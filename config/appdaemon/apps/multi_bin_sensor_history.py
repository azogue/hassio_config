# -*- coding: utf-8 -*-
"""
Binary sensor custom history as AppDaemon App for Home Assistant.

Listen to multiple binary sensors to reflect the last activation,
maintaining a history of the lasts activations.

* Sensor State: `Friendly name`
* Sensor attributes:
    `history_1: Friendly name: activation_timestamp`,
    `history_2: Friendly name: activation_timestamp`,
    ...

Yaml config goes like this:

```yaml
LastMotionHistory:
  class: MultiBinSensor
  module: multi_bin_sensor_history
  new_entity: sensor.last_motion
  max_history: 10
  binary_sensors:
    binary_sensor.hue_motion_sensor_1_motion: Cocina
    binary_sensor.hue_motion_sensor_2_motion: Office
  format_last_changed: '%H:%M:%S'
  icon: mdi:motion-sensor
  friendly_name: Last motion
```

"""
from collections import deque
from typing import Deque, Dict

import appdaemon.plugins.hass.hassapi as hass

_ATTR_NAME = "history_"


class MultiBinSensor(hass.Hass):

    _entity: str
    _date_format: str
    _history: Deque[str]
    _friendly_names: Dict[str, str]
    _entity_attributes: Dict[str, str]

    def initialize(self):
        """AppDaemon required method for app init."""
        self._entity = self.args.get("new_entity")
        icon = self.args.get("icon", "mdi:motion-sensor")
        friendly_name = self.args.get("friendly_name", "Last motion")
        self._entity_attributes = {"icon": icon, "friendly_name": friendly_name}
        self._date_format = self.args.get("format_last_changed")

        # Set up state history for attributes
        self._history = deque([], maxlen=int(self.args.get("max_history")))

        # Listen for binary sensor activations and store friendly names for them
        bin_sensors: Dict[str, str] = self.args.get("binary_sensors")
        self._friendly_names = {}
        for sensor, pretty_name in bin_sensors.items():
            self._friendly_names[sensor] = pretty_name
            self.listen_state(self._bin_sensor_activation, sensor, new="on")

        # recover old values, if any
        old_attrs = self.get_state(self._entity, attribute="all")
        if old_attrs:
            state = old_attrs.get("state", "unknown")
            for k, old_value in reversed(old_attrs.get("attributes", {}).items()):
                if k.startswith(_ATTR_NAME) and ": " in old_value:
                    self._history.append(old_value)
            # Re-Publish old state
            self._set_new_sensor_state(state)

    def _set_new_sensor_state(self, state):
        """Publish a new state for the sensor."""
        history_attrs = {
            f"{_ATTR_NAME}{i}": old_state
            for i, old_state in enumerate(reversed(self._history))
            if i > 0
        }
        attributes = {**self._entity_attributes, **history_attrs}
        self.set_state(self._entity, state=state, attributes=attributes)

    def _bin_sensor_activation(self, entity, attribute, old, new, kwargs):
        """Listen to bin sensors turning on, update history and publish a new state."""
        location = self._friendly_names[entity]
        pretty_date_now = self.datetime().strftime(self._date_format)

        # Add to history
        self._history.append(f"{location}: {pretty_date_now}")

        # Publish new state
        self._set_new_sensor_state(location)
