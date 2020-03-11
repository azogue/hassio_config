# -*- coding: utf-8 -*-
from time import monotonic
from typing import Any, Dict, Optional

import appdaemon.plugins.hass.hassapi as hass

LOGGER = "motion_log"
EVENT_LOG_LEVEL = "DEBUG"  # "INFO"

DELAY_TO_RE_ENABLE_MOTION_CONTROL = 120

# Time with light enabled after last sensor is off
WAIT_TO_TURN_OFF_MORNING = 120
WAIT_TO_TURN_OFF_MIDDAY = 300  # After last sensor is off
WAIT_TO_TURN_OFF_AFTERNOON = 150  # After last sensor is off
WAIT_TO_TURN_OFF_NIGHT = 60  # After last sensor is off
WAIT_TO_TURN_OFF_DEEP_NIGHT = 30  # After last sensor is off

LIGHT_GROUP = "light.cocina"
LIGHT_COLORED = "light.tira_cocina"
HUE_SWITCH = "remote.interruptor_cocina"
MOTION_SENSORS = (
    "input_boolean.mirror_hue_motion_1"
    ",binary_sensor.hue_motion_sensor_1_motion"
    ",binary_sensor.sensor_kitchen_mov1"
)
SCENES = {
    # between("01:00:00", "06:00:00")
    "kitchen_deep_night": (
        "light/turn_on",
        {
            "entity_id": LIGHT_COLORED,
            "xy_color": [0.167, 0.268],
            "brightness": 199,
            "transition": 2,
        },
        WAIT_TO_TURN_OFF_DEEP_NIGHT,
    ),
    # between("sunset - 00:30:00", "sunrise + 00:15:00")
    "kitchen_night": (
        "hue/hue_activate_scene",
        {"scene_name": "Lectura", "group_name": "Cocina"},
        WAIT_TO_TURN_OFF_NIGHT,
    ),
    # between("sunrise + 00:14:00", "13:00:01")
    "kitchen_energy": (
        "hue/hue_activate_scene",
        {"scene_name": "Energía", "group_name": "Cocina"},
        WAIT_TO_TURN_OFF_MORNING,
    ),
    # between("13:00:00", "17:00:01")
    "kitchen_concentrate": (
        "hue/hue_activate_scene",
        {"scene_name": "Concentración", "group_name": "Cocina"},
        WAIT_TO_TURN_OFF_MIDDAY,
    ),
    # between("17:00:00", "sunset - 00:30:01")
    "kitchen_reading": (
        "light/turn_on",
        {
            "entity_id": LIGHT_GROUP,
            "profile": "reading",
            "brightness": 254,
            "transition": 2,
        },
        WAIT_TO_TURN_OFF_AFTERNOON,
    ),
}


# noinspection PyClassHasNoInit
class HueSwitchAndMotionControl(hass.Hass):
    """
    App to automate lights in a room with:
    - One or more motion sensors
    - A Hue Dimmer Switch for manual control, with priority over automatic.
    """

    _main_constrain: str
    _light_on: bool
    _motion_on: bool
    _motion_light_enabled: bool
    _last_switch_press: float

    _motion_states: Dict[str, Any]
    _handler_turn_off_lights = None
    _handler_light_enabler = None

    def initialize(self):
        """Set up appdaemon app."""
        light_st = self.get_state(LIGHT_GROUP)
        self._light_on = light_st == "on"
        self._main_constrain = "input_boolean.app_lights_automation"
        self._last_switch_press = 0.0

        self._motion_states = {}
        for sensor in MOTION_SENSORS.split(","):
            self._motion_states[sensor] = self.get_state(sensor) == "on"
            self.listen_state(
                self._motion_detected,
                sensor,
                constrain_input_boolean=self._main_constrain,
            )
        self._motion_on = any(self._motion_states.values())
        self._motion_light_enabled = True
        self.log(
            f"APP INIT with light {light_st}, motion: {self._motion_states}",
            level="WARNING",
            log=LOGGER,
        )
        self.listen_state(self._light_changed, LIGHT_GROUP)
        self.listen_event(
            self._switch_event,
            "hue_switch_kitchen_triggered",
            constrain_input_boolean=self._main_constrain,
        )

    def _turn_lights_off(self, *_args, **_kwargs):
        self.log(f"APAGA LUCES -------------", level="WARNING", log=LOGGER)
        self.call_service(
            "light/turn_off", entity_id=LIGHT_GROUP, transition=1
        )
        self._light_on = False
        self._handler_turn_off_lights = None

    def _select_scene(self):
        if self.now_is_between("01:00:00", "06:00:00"):
            scene_key = "kitchen_deep_night"
        elif self.now_is_between("sunset - 00:30:00", "sunrise + 00:15:00"):
            scene_key = "kitchen_night"
        elif self.now_is_between("sunrise + 00:14:00", "13:00:01"):
            # kitchen_energy
            scene_key = "kitchen_energy"
        elif self.now_is_between("13:00:00", "17:00:01"):
            # kitchen_concentrate
            scene_key = "kitchen_concentrate"
        else:  # if self.now_is_between("17:00:00", "sunset - 00:30:01"):
            # kitchen_reading
            scene_key = "kitchen_reading"

        return scene_key

    def _turn_lights_on(self, entity: str, *_args, **_kwargs):
        scene_key = self._select_scene()
        service, params, _ = SCENES[scene_key]
        self.call_service(service, **params)
        self._light_on = True
        self.log(
            f"ENCIENDE LUCES [{scene_key}] from {entity}",
            level="WARNING",
            log=LOGGER,
        )

    def _reset_inactivity_timer(
        self, new_wait: Optional[int] = None, entity_id: str = ""
    ):
        if self._handler_turn_off_lights is not None:
            self.cancel_timer(self._handler_turn_off_lights)
            self._handler_turn_off_lights = None
            if new_wait is None:
                self.log(
                    f"Reset wait counter from {entity_id}",
                    level=EVENT_LOG_LEVEL,
                    log=LOGGER,
                )
        if new_wait is not None:
            self.log(
                f"Set timer of {new_wait} s from deactivated {entity_id}",
                level=EVENT_LOG_LEVEL,
                log=LOGGER,
            )
            self._handler_turn_off_lights = self.run_in(
                self._turn_lights_off, new_wait
            )

    def _enable_motion_lights(self, *_args, **_kwargs):
        self._reset_light_enabler()
        self._motion_light_enabled = True
        self.log(f"Enabled motion lights after manual usage", log=LOGGER)

    def _reset_light_enabler(self, new_wait: Optional[int] = None):
        if self._handler_light_enabler is not None:
            self.cancel_timer(self._handler_light_enabler)
            self._handler_light_enabler = None
        if new_wait is not None:
            self._handler_light_enabler = self.run_in(
                self._enable_motion_lights, new_wait
            )
            self.log(
                f"Re-enable light control in {new_wait} s",
                level=EVENT_LOG_LEVEL,
                log=LOGGER,
            )

    def _light_changed(self, _entity, _attribute, old, new, _kwargs):
        """
        Listener to changes on light, to catch external ones,
        not only manual usages of hue dimmer switch.
        """
        is_on = new == "on"
        is_off = new == "off"
        if is_on and old == "off":
            if not self._light_on:
                self.log(
                    "UNSYNCED ON LIGHT (stored as off)",
                    level="WARNING",
                    log=LOGGER,
                )
            self._light_on = True
        elif is_off and old == "on":
            if self._light_on:
                self.log(
                    "UNSYNCED OFF LIGHT (stored as on)",
                    level="WARNING",
                    log=LOGGER,
                )
            self._light_on = False
        elif not is_on and not is_off:
            self.log(
                f"Unavailable LIGHT? {new} (stored as {old})", log=LOGGER,
            )
        else:
            self._light_on = is_on

    def _switch_event(self, _event, _event_data, *_args, **_kwargs):
        """
        Listener to manual press on Hue dimmer switch (for manual usage)

        Usually 2 events are received: 'X_click' and 'X_click_up',
        but the first one can be missed.

        When ON/OFF buttons are used, motion lights are disabled for some time.
        """
        ts_now = monotonic()
        delta = ts_now - self._last_switch_press
        self._last_switch_press = ts_now
        new = self.get_state(HUE_SWITCH)
        self.log(
            f"MANUAL SWITCH -> {new} (delta_T={delta:.1f}s)",
            level="WARNING",
            log=LOGGER,
        )
        if self._motion_light_enabled and new.startswith("4_click"):
            self._motion_light_enabled = False
            self._light_on = False
            self._motion_on = False
            self._reset_inactivity_timer(entity_id=HUE_SWITCH)
            self._reset_light_enabler(DELAY_TO_RE_ENABLE_MOTION_CONTROL)
        elif self._motion_light_enabled and new.startswith("1_click"):
            self._motion_light_enabled = False
            self._light_on = True
            self._motion_on = False
            self._reset_light_enabler(5 * SCENES[self._select_scene()][2])
            self._reset_inactivity_timer(entity_id=HUE_SWITCH)

    def _motion_detected(self, entity, _attribute, old, new, _kwargs):
        """
        Listener to motion sensor changes.

        * New activated motion sensor turns on lights, if motion lights enabled
        * Each activated motion sensor resets the wait timer, if previously set
        * Last deactivated sensor sets a new wait timer to turn off lights.
        """
        activated = new == "on"
        if not self._motion_light_enabled:
            if activated and self._light_on:
                # reset wait for enable automatic control (4x mult)
                self._reset_light_enabler(4 * SCENES[self._select_scene()][2])
            return

        self.log(
            f"Event: {entity:<25} -> {new:<3} (was {old})",
            level=EVENT_LOG_LEVEL,
            log=LOGGER,
        )
        self._motion_states[entity] = activated
        any_active = any(self._motion_states.values())
        if not self._motion_on and activated:
            # turn lights on (1st time)
            self._motion_on = True
            self._reset_inactivity_timer(entity_id=entity)
            if not self._light_on:
                self._turn_lights_on(entity)

        elif self._motion_on and not activated and not any_active:
            self._motion_on = False
            # wait some time before turning lights off
            self._reset_inactivity_timer(
                new_wait=SCENES[self._select_scene()][2], entity_id=entity
            )
        else:
            self._motion_on = any_active
            if activated:
                self._reset_inactivity_timer(entity_id=entity)
