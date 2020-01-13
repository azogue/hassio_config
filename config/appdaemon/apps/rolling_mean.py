from time import monotonic

import appdaemon.plugins.hass.hassapi as hass


# noinspection PyClassHasNoInit
class RollingMean(hass.Hass):
    """App that evaluates a rolling mean for X time window over some sensor."""

    _bag_values: dict = None
    _rolling_mean: float = None
    _window: int = None
    _sensor_entity: str = None
    _sensor_frequency: str = None
    _rolling_sensor_name: str = None

    def initialize(self):
        """Set up App."""
        self._rolling_sensor_name = self.args.get('name')
        self._sensor_entity = self.args.get('sensor')
        self._sensor_frequency = self.args.get('sensor_freq')
        self._window = self.args.get('window_seconds')

        self._bag_values = {
            # time: sensor_known_value
        }

        self.listen_state(self._update_rolling_mean, self._sensor_entity)
        self.log(
            f"Rolling mean of {self._window} sec initialized for "
            f"{self._sensor_entity}[F={self._sensor_frequency}] in "
            f"new {self._rolling_sensor_name}"
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
        try:
            value = int(new)
        except ValueError:
            self.log(
                f"Bad new value: {new} for {entity}, doing nothing."
            )
            return

        # valid sensor measure
        ts = round(monotonic())
        limit = ts - self._window
        for k in filter(lambda x: x < limit, self._bag_values):
            self._bag_values.pop(k)

        self._bag_values[ts] = value
        new_rm_value = round(
            sum(self._bag_values.values()) / len(self._bag_values), 0
        )
        self._rolling_mean = new_rm_value

        self.set_state(
            self._rolling_sensor_name,
            state=new_rm_value,
            attributes=self.rolling_sensor_attributes,
        )
