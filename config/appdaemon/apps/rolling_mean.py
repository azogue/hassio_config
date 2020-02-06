from concurrent.futures import TimeoutError
from time import monotonic

import appdaemon.plugins.hass.hassapi as hass

LOGGER = "event_log"


# noinspection PyClassHasNoInit
class RollingMean(hass.Hass):
    """App that evaluates a rolling mean for X time window over some sensor."""

    _window: int = None
    _sensor_frequency: int = None
    _sensor_entity: str = None
    _rolling_sensor_name: str = None

    _bag_values: dict
    _rolling_mean: float
    _counter_samples: int
    _last_sample_ok: bool

    def initialize(self):
        """Set up App."""
        self._rolling_sensor_name = self.args.get('name')
        self._sensor_entity = self.args.get('sensor')
        self._sensor_frequency = int(self.args.get('sensor_freq'))
        self._window = int(self.args.get('window_seconds'))
        self._counter_samples = 0
        self._last_sample_ok = True

        aprox_sample_number = int(self._window / self._sensor_frequency)
        init_value = self.get_state(self._sensor_entity)
        try:
            init_value = float(init_value)
        except ValueError:
            self.log("Bad init (no known state)", log=LOGGER)
            init_value = 500.0

        init_ts = round(monotonic()) - self._sensor_frequency
        self._bag_values = {
            # time: sensor_known_value
            init_ts - i * self._sensor_frequency: init_value
            for i in range(aprox_sample_number)
        }

        self.listen_state(self._update_rolling_mean, self._sensor_entity)
        self.log(
            f"Rolling mean of {self._window} sec initialized for "
            f"{self._sensor_entity}[F={self._sensor_frequency}] in "
            f"new {self._rolling_sensor_name} with {init_value} W",
            log=LOGGER,
        )

    @property
    def rolling_sensor_attributes(self) -> dict:
        return {
            "unit_of_measurement": "W",
            "friendly_name": "Consumo sostenido",
            "icon": "mdi:flash",
            "num_values": len(self._bag_values),
            "min_value": min(self._bag_values.values()),
            "max_value": max(self._bag_values.values()),
            "age_max": max(self._bag_values) - min(self._bag_values),
        }

    # noinspection PyUnusedLocal
    def _update_rolling_mean(self, entity, attribute, old, new, kwargs):
        """Update sensor rm."""
        if new == "unknown":
            # if not self._last_sample_ok: # repeated error
            self.log(f"Received unknown value!", level="WARNING", log=LOGGER)
            self._last_sample_ok = False
            return

        try:
            value = int(new)
            self._counter_samples += 1
            if not self._last_sample_ok:
                self.log(
                    f"Recovered good value: {value}, all ok again", log=LOGGER
                )
                self._last_sample_ok = True
        except ValueError:
            self.log(
                f"Bad new value: {new} for {entity}, doing nothing.",
                level="ERROR",
                log=LOGGER,
            )
            return

        # valid sensor measure
        ts = round(monotonic())
        limit = ts - self._window
        for k in filter(lambda x: x < limit, list(self._bag_values.keys())):
            self._bag_values.pop(k)

        self._bag_values[ts] = value
        new_rm_value = round(
            sum(self._bag_values.values()) / len(self._bag_values), 0
        )
        self._rolling_mean = new_rm_value

        if self._counter_samples % 3 == 0:
            try:
                self.set_state(
                    self._rolling_sensor_name,
                    state=new_rm_value,
                    attributes=self.rolling_sensor_attributes,
                )
            except TimeoutError:
                self.log(
                    f"TimeoutError on state set :(", level="ERROR", log=LOGGER
                )
