# -*- coding: utf-8 -*-
"""
AppDaemon App to create a Time-Weighted Moving Average sensor over another one.

Conceived for those sensors without a periodic update interval,
where the more common moving averages based on a number of samples
are not a valid solution, nor is the one with the stats sensor with max_age,
which is using the same weight for each sample
(so it only really works for periodic signals!)

This app *weights* each sample with the time delta passed since the last one :)
and also publishes the TWMA sensor state *with a fixed update interval*
(instead of updating when the base sensor is updated)

It also persist the state between runs by storing the samples of each
sensor in a .csv file (as _poor man restore system_)

```yaml
StatsSensors:
  module: time_weighted_moving_average
  class: TimeWeightedMovingAverage
  update_interval: 30
  sensors:
    - sensor_source: sensor.main_power_total
      sensor_publish: sensor.sustained_power_weighted
      name: Power (contador)
      window_minutes: 15
      expected_interval: 5
      precision: 0
    - sensor_source: sensor.temperatura_exterior
      sensor_publish: sensor.temperatura_ext_stats_mean
      name: Temperatura exterior
      window_minutes: 15
      expected_interval: 15
      precision: 1
```

"""
import csv
from datetime import datetime, timedelta
from collections import deque
from math import ceil
from pathlib import Path
from typing import Dict, Optional

import appdaemon.plugins.hass.hassapi as hass
import attr

LOGGER = "event_log"
LOG_LEVEL = "INFO"


@attr.s
class RollingSensorData:
    source_entity: str = attr.ib()
    sensor_entity: str = attr.ib()
    sensor_name: str = attr.ib()
    max_age: timedelta = attr.ib()
    precision: int = attr.ib()

    current_samples: deque = attr.ib()
    ts_last: Optional[datetime] = attr.ib()
    default_delta: timedelta = attr.ib()
    sensor_attrs: dict = attr.ib()


def _write_state(path_csv: Path, sensor_data: RollingSensorData):
    with open(path_csv, 'w') as csvfile:
        writer = csv.writer(csvfile)
        for (value_i, ts_i, delta_i) in sensor_data.current_samples:
            value_i: float
            ts_i: datetime
            delta_i: timedelta
            writer.writerow([value_i, ts_i.isoformat(), delta_i.total_seconds()])


def _read_state(path_csv: Path, sensor_data: RollingSensorData):
    with open(path_csv, 'r') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            value_i: float = float(row[0])
            ts_i: datetime = datetime.fromisoformat(row[1])
            delta_i: timedelta = timedelta(seconds=float(row[2]))
            sensor_data.current_samples.append(
                (value_i, ts_i, delta_i)
            )
    if sensor_data.current_samples:
        sensor_data.ts_last = sensor_data.current_samples[-1][1]


# noinspection PyClassHasNoInit
class TimeWeightedMovingAverage(hass.Hass):
    """
    App to generate a sensor with a TWMA from another HA sensor.
    """

    _update_interval: timedelta = None
    _handler_timer = None
    _sensors: Dict[str, RollingSensorData] = None

    def initialize(self):
        """AppDaemon required method for app init."""
        self._update_interval = timedelta(
            seconds=int(self.args.get("update_interval", 30))
        )
        self._sensors = {}

        for sensor_config in self.args.get("sensors"):
            source_entity = sensor_config.get("sensor_source")
            source_attrs: dict = self.get_state(source_entity, attribute="all")
            icon = "mdi:homeassistant"
            unit = "%"
            if source_attrs and "attributes" in source_attrs:
                icon = source_attrs["attributes"].get("icon", "mdi:homeassistant")
                unit = source_attrs["attributes"].get("unit_of_measurement")

            # TODO implement history
            # start_time = datetime.datetime.now() - timedelta(days=2)
            # data = self.get_history("light.office_lamp", start_time=start_time)

            sensor_entity = sensor_config.get("sensor_publish")
            sensor_name = sensor_config.get("name")
            precision = int(sensor_config.get("precision", 1))
            max_age = timedelta(
                minutes=int(sensor_config.get("window_minutes", 15))
            )
            default_delta = timedelta(
                seconds=int(sensor_config.get("expected_interval", 5))
            )
            maxlen = ceil(2 * max_age / default_delta)
            current_samples = deque(
                [], maxlen=maxlen
            )
            sensor_attrs = {
                "icon": icon,
                "friendly_name": sensor_name,
                "unit_of_measurement": unit,
                "max_age": max_age,
                "source": source_entity,
                "default_delta": default_delta,
                "max_len": maxlen,
            }

            assert source_entity not in self._sensors
            sensor_data = RollingSensorData(
                source_entity=source_entity,
                sensor_entity=sensor_entity,
                sensor_name=sensor_name,
                max_age=max_age,
                precision=precision,
                current_samples=current_samples,
                ts_last=None,
                default_delta=default_delta,
                sensor_attrs=sensor_attrs,
            )
            path_csv = Path("/config/appdaemon/apps") / f'{sensor_entity}.csv'
            if path_csv.exists():
                self.log(
                    f"Reading values from path_csv: {path_csv}",
                    level="WARNING",
                    log=LOGGER,
                )
                _read_state(path_csv, sensor_data)
            else:
                self.log(
                    f"Not found CSV for {sensor_entity} in {path_csv}",
                    level="ERROR",
                    log=LOGGER,
                )
            self._sensors[source_entity] = sensor_data

        # Listen for source changes:
        for source_sensor in self._sensors:
            self.listen_state(self.source_change, source_sensor)

        self._handler_timer = self.run_every(
            self.publish_states,
            self.datetime() + (self._update_interval / 2),
            self._update_interval.total_seconds()
        )

        pairs = {
            source: s.sensor_entity for source, s in self._sensors.items()
        }
        self.log(
            f"TimeWeightedMovingAverage Initialized for {pairs}",
            level=LOG_LEVEL,
            log=LOGGER,
        )

    def terminate(self):
        path_base = Path("/config/appdaemon/apps")
        for sensor_data in self._sensors.values():
            if not sensor_data.current_samples:
                continue

            path_csv = path_base / f'{sensor_data.sensor_entity}.csv'
            self.log(
                f"Writing values in path_csv: {path_csv}",
                level="WARNING",
                log=LOGGER,
            )
            _write_state(path_csv, sensor_data)

    def source_change(self, entity, attribute, old, new, _kwargs):
        """Add new samples as they come in."""
        sensor = self._sensors[entity]
        try:
            value = float(new)
        except (ValueError, TypeError) as exc:
            self.error("Bad source value: %s -> %s", new, exc)
            sensor.ts_last = None
            return

        now = datetime.now()
        if sensor.ts_last is None:
            sensor.ts_last = now - sensor.default_delta

        delta = now - sensor.ts_last
        sensor.ts_last = now
        sensor.current_samples.append(
            (value, now, delta)
        )

    def _publish_sensor(self, now: datetime, sensor_data: RollingSensorData):
        """Process samples and publish sensors states."""
        min_ts = now - sensor_data.max_age
        acc_time = timedelta(0)
        acc_weight = acc_values = 0
        num_expired_samples = 0
        num_valid_samples = 0

        for (value_i, ts_i, delta_i) in sensor_data.current_samples:
            if ts_i < min_ts:
                num_expired_samples += 1
                continue

            num_valid_samples += 1
            acc_time += delta_i
            acc_weight += value_i * delta_i.total_seconds()
            acc_values += value_i

        # remove expired
        for _ in range(num_expired_samples):
            sensor_data.current_samples.popleft()

        # empty sensor, special publish
        if not num_valid_samples or not acc_time:
            sensor_attrs = {
                "num_samples": num_valid_samples,
                "num_expired_samples": num_expired_samples,
                "time_window": acc_time,
                **sensor_data.sensor_attrs,
            }
            self.set_state(
                sensor_data.sensor_entity, state="unknown", attributes=sensor_attrs
            )
            return

        # compute stats
        time_weighted_moving_average = acc_weight / acc_time.total_seconds()
        simple_moving_average = acc_values / num_valid_samples

        wma = round(time_weighted_moving_average, sensor_data.precision)
        ma = round(simple_moving_average, sensor_data.precision)
        if sensor_data.precision == 0:
            wma, ma = int(wma), int(ma)
        sensor_attrs = {
            "weighted_moving_average": wma,
            "moving_average": ma,
            "num_samples": num_valid_samples,
            "num_expired_samples": num_expired_samples,
            "time_window": acc_time,
            **sensor_data.sensor_attrs,
        }

        self.set_state(
            sensor_data.sensor_entity, state=wma, attributes=sensor_attrs
        )

    def publish_states(self, *args, **kwargs):
        """Process samples and publish sensors states."""
        now = datetime.now()
        for sensor_data in self._sensors.values():
            ts_last = sensor_data.ts_last
            if ts_last is None or (now - ts_last) > sensor_data.default_delta:
                # get state anyway
                value = self.get_state(sensor_data.source_entity)
                self.source_change(
                    # entity, _attribute, _old, new
                    sensor_data.source_entity, None, None, value, {},
                )

            self._publish_sensor(now, sensor_data)
