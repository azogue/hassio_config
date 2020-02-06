# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant
"""
import datetime as dt

import appdaemon.plugins.hass.hassapi as hass

TAP_SENSOR = "sensor.interruptor_exterior"
COVER_WINDOW = "cover.persiana_ventanal"
COVER_DOOR = "cover.puerta_terraza"
SWITCH_AMBI = "switch.ambilight_plus_hue"
LIGHT_TOGGLE = "light.terraza"
LIGHT_PARAMS_AFTER_AMBI = {
    "entity_id": "light.salon",
    "transition": 3,
    "profile": "relax",
    "brightness": 254,
}
LOGGER = "event_log"


# noinspection PyClassHasNoInit
class HueTapControl(hass.Hass):
    """App to run commands when Hue Tap is clicked."""

    def initialize(self):
        """Set up appdaemon app."""
        self.listen_state(self._tap_used, TAP_SENSOR)

    def _tap_used(self, entity, attribute, old, new, kwargs):
        if new == "1_click":  # toggle terraza
            self.call_service("light/toggle", entity_id=LIGHT_TOGGLE)
            self.log(
                f"Tap was used: {new} (before it was {old}) "
                f"--> terraza is {self.get_state(LIGHT_TOGGLE)}",
                log=LOGGER,
            )
        elif new == "2_click":  # adjust cover ventanal
            st_cover_pos = int(self.get_state(COVER_WINDOW, attribute="attributes")["current_position"])
            if st_cover_pos > 90:
                # set position 30
                self.call_service("cover/set_cover_position", entity_id=COVER_WINDOW, position=30)
                self.log(
                    f"Adjusting cover ventanal to 30 (was {st_cover_pos})",
                    log=LOGGER,
                )
            else:
                # set position 100 (open)
                self.call_service("cover/open_cover", entity_id=COVER_WINDOW)
                self.log(
                    f"OPEN cover ventanal (was {st_cover_pos})",
                    log=LOGGER,
                )
        elif new == "3_click":  # adjust ambilight
            st_amb = self.get_state(SWITCH_AMBI)
            if st_amb == "off":
                self.call_service("switch/turn_on", entity_id=SWITCH_AMBI)
                self.log(f"Adjust Hue+ambilight to ON", log=LOGGER)
            else:
                self.call_service("switch/turn_off", entity_id=SWITCH_AMBI)
                self.call_service("light/turn_on", **LIGHT_PARAMS_AFTER_AMBI)
                self.log(f"Adjust Hue+ambilight to OFF", log=LOGGER)
        elif new == "4_click":  # adjust cover puerta
            st_cover_pos = int(self.get_state(COVER_DOOR, attribute="attributes")["current_position"])
            if st_cover_pos > 90:
                # set position 60
                self.call_service("cover/set_cover_position", entity_id=COVER_DOOR, position=60)
                self.log(
                    f"Adjusting cover puerta to 60 (was {st_cover_pos})",
                    log=LOGGER,
                )
            else:
                # set position 100 (open)
                self.call_service("cover/open_cover", entity_id=COVER_DOOR)
                self.log(
                    f"OPEN cover puerta (was {st_cover_pos})", log=LOGGER
                )
