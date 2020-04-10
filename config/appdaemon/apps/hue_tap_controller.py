# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant
"""
import appdaemon.plugins.hass.hassapi as hass

TAP_BUTTONS = {
    34: "1_click",
    16: "2_click",
    17: "3_click",
    18: "4_click",
}
COVER_WINDOW = "cover.shelly_ventanal"
COVER_DOOR = "cover.shelly_puerta"
SWITCH_AMBI = "switch.ambilight_plus_hue"
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
        self.listen_event(
            self._tap_event_triggered,
            "deconz_event",
            id="interruptor_exterior",
        )

    def _tap_event_triggered(self, _event_name, event_data, *_args, **_kwargs):
        tap_code = TAP_BUTTONS[event_data["event"]]
        # if tap_code == "1_click":  # toggle terraza already setup in deconz
        if tap_code == "3_click":  # adjust ambilight
            st_amb = self.get_state(SWITCH_AMBI)
            if st_amb == "off":
                self.call_service("switch/turn_on", entity_id=SWITCH_AMBI)
                self.log(f"Adjust Hue+ambilight to ON", log=LOGGER)
            else:
                self.call_service("switch/turn_off", entity_id=SWITCH_AMBI)
                self.call_service("light/turn_on", **LIGHT_PARAMS_AFTER_AMBI)
                self.log(f"Adjust Hue+ambilight to OFF", log=LOGGER)

        elif tap_code == "2_click":  # adjust cover ventanal
            cover_attrs = self.get_state(COVER_WINDOW, attribute="attributes")
            st_cover_pos = int(cover_attrs["current_position"])
            if st_cover_pos > 90:
                # set position 30
                self.call_service(
                    "cover/set_cover_position",
                    entity_id=COVER_WINDOW,
                    position=30,
                )
                self.log(
                    f"Adjusting cover ventanal to 30 (was {st_cover_pos})",
                    log=LOGGER,
                )
            else:
                # set position 100 (open)
                self.call_service("cover/open_cover", entity_id=COVER_WINDOW)
                self.log(
                    f"OPEN cover ventanal (was {st_cover_pos})", log=LOGGER,
                )
        elif tap_code == "4_click":  # adjust cover puerta
            cover_attrs = self.get_state(COVER_DOOR, attribute="attributes")
            st_cover_pos = int(cover_attrs["current_position"])
            if st_cover_pos > 90:
                # set position 60
                self.call_service(
                    "cover/set_cover_position",
                    entity_id=COVER_DOOR,
                    position=60,
                )
                self.log(
                    f"Adjusting cover puerta to 60 (was {st_cover_pos})",
                    log=LOGGER,
                )
            else:
                # set position 100 (open)
                self.call_service("cover/open_cover", entity_id=COVER_DOOR)
                self.log(f"OPEN cover puerta (was {st_cover_pos})", log=LOGGER)
