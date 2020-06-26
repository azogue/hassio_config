# -*- coding: utf-8 -*-
"""
Appdaemon app for motion + switch control of light in a room.
"""
from time import monotonic
from typing import Any, Dict, Optional

import appdaemon.plugins.hass.hassapi as hass

LOGGER = "motion_log"
EVENT_LOG_LEVEL = "DEBUG"  # "INFO"

# Used entities
LIGHT_GROUP = "light.cocina"
LISTEN_EVENT = "deconz_event"
LISTEN_EVENT_ID = "interruptor_cocina"
MOTION_CONTROL_CONSTRAIN = "input_boolean.app_lights_automation"

MOTION_SENSOR_MAIN = "binary_sensor.motion_sensor_cocina"
MOTION_SENSOR_SECONDARY = "binary_sensor.mini_motion_cocina"
MOTION_SENSOR_AUX = "binary_sensor.sensor_kitchen_mov1"

DELAY_TO_RE_ENABLE_MOTION_CONTROL = 120
MAX_DELAY_MOTION_OFF = 900

# Time with light enabled after last sensor is off
WAIT_TO_TURN_OFF_MORNING = 120
WAIT_TO_TURN_OFF_MIDDAY = 300  # After last sensor is off
WAIT_TO_TURN_OFF_AFTERNOON = 150  # After last sensor is off
WAIT_TO_TURN_OFF_NIGHT = 60  # After last sensor is off
WAIT_TO_TURN_OFF_DEEP_NIGHT = 30  # After last sensor is off

RWL_BUTTONS = {
    1000: "1_click",
    2000: "2_click",
    3000: "3_click",
    4000: "4_click",
    1001: "1_hold",
    2001: "2_hold",
    3001: "3_hold",
    4001: "4_hold",
    1002: "1_click_up",
    2002: "2_click_up",
    3002: "3_click_up",
    4002: "4_click_up",
    1003: "1_hold_up",
    2003: "2_hold_up",
    3003: "3_hold_up",
    4003: "4_hold_up",
}

SCENE_DEEP_NIGHT = "kitchen_deep_night"
SCENE_NIGHT = "kitchen_night"
SCENE_ENERGY = "kitchen_energy"
SCENE_CONCENTRATION = "kitchen_concentrate"
SCENE_READING = "kitchen_reading"

SCENE_ROTATION = {
    SCENE_NIGHT: 0,
    SCENE_DEEP_NIGHT: 1,
    SCENE_ENERGY: 2,
    SCENE_CONCENTRATION: 3,
    SCENE_READING: 4,
}
DECONZ_SCENES = {
    # between("01:00:00", "06:00:00")
    SCENE_DEEP_NIGHT: ("cocina_deep_night", WAIT_TO_TURN_OFF_DEEP_NIGHT),
    # between("sunset - 00:30:00", "sunrise + 00:15:00")
    SCENE_NIGHT: ("cocina_night", WAIT_TO_TURN_OFF_NIGHT),
    # between("sunrise + 00:14:00", "13:00:01")
    SCENE_ENERGY: ("cocina_energy", WAIT_TO_TURN_OFF_MORNING),
    # between("13:00:00", "17:00:01")
    SCENE_CONCENTRATION: ("cocina_concentration", WAIT_TO_TURN_OFF_MIDDAY),
    # between("17:00:00", "sunset - 00:30:01")
    SCENE_READING: ("cocina_reading", WAIT_TO_TURN_OFF_AFTERNOON),
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
    _last_light_on: float
    _last_scene: str

    _motion_states: Dict[str, Any]
    _handler_turn_off_lights = None
    _handler_light_enabler = None

    def initialize(self):
        """Set up appdaemon app."""
        light_st = self.get_state(LIGHT_GROUP)
        self._light_on = light_st == "on"
        self._main_constrain = MOTION_CONTROL_CONSTRAIN
        self._last_switch_press = 0.0
        self._last_scene = SCENE_ENERGY

        self._motion_states = {}
        for sensor in [MOTION_SENSOR_MAIN, MOTION_SENSOR_SECONDARY, MOTION_SENSOR_AUX]:
            self._motion_states[sensor] = self.get_state(sensor) == "on"
            self.listen_state(
                self._motion_detected,
                sensor,
                constrain_input_boolean=self._main_constrain,
            )
        self._motion_on = any(self._motion_states.values())
        self._last_light_on = 0.0 if not self._motion_on else monotonic()
        self._motion_light_enabled = True

        self.listen_state(self._light_changed, LIGHT_GROUP)
        self.listen_event(self._switch_event, LISTEN_EVENT, id=LISTEN_EVENT_ID)
        # Add listener to check light off after a long time
        self.listen_state(
            self._no_motion_for_long_time,
            MOTION_SENSOR_MAIN,
            new="off",
            duration=MAX_DELAY_MOTION_OFF,
            # constrain_input_boolean=self._main_constrain,
        )
        self.log(
            f"APP INIT with light {light_st}, motion: {self._motion_states}",
            level="WARNING",
            log=LOGGER,
        )

    def _turn_lights_off(self, *_args, **kwargs):
        transition = kwargs.get("transition", 1)
        self.call_service(
            "light/turn_off", entity_id=LIGHT_GROUP, transition=transition
        )
        self._light_on = False
        if self._handler_turn_off_lights is not None:
            self.cancel_timer(self._handler_turn_off_lights)
            self._handler_turn_off_lights = None

        # Log off operation with ∆T on
        delta_on = monotonic() - self._last_light_on
        if "manual" in kwargs:
            self.log(
                f"MANUAL OFF (delta_T={delta_on / 60:.1f} min) ---", log=LOGGER
            )
        else:
            self.log(
                f"AUTO OFF (delta_T={delta_on / 60:.1f} min) -----",
                level="WARNING",
                log=LOGGER,
            )

    def _select_scene(self):
        if self.now_is_between("01:00:00", "06:00:00"):
            scene_key = SCENE_DEEP_NIGHT
        elif self.now_is_between("sunset - 00:30:00", "sunrise + 00:15:00"):
            scene_key = SCENE_NIGHT
        elif self.now_is_between("sunrise + 00:14:00", "13:00:01"):
            # kitchen_energy
            scene_key = SCENE_ENERGY
        elif self.now_is_between("13:00:00", "17:00:01"):
            # kitchen_concentrate
            scene_key = SCENE_CONCENTRATION
        else:  # if self.now_is_between("17:00:00", "sunset - 00:30:01"):
            # kitchen_reading
            scene_key = SCENE_READING

        return scene_key

    def _get_current_delay(self):
        return DECONZ_SCENES[self._select_scene()][1]

    def _max_switch_delay(self):
        return 5 * DECONZ_SCENES[self._select_scene()][1]

    def _turn_lights_on(self, origin: str, scene_key: Optional[str] = None):
        level = "INFO"
        if scene_key is None:
            level = "WARNING"
            scene_key = self._select_scene()
        scene_name, _ = DECONZ_SCENES[scene_key]
        self.call_service("scene/turn_on", entity_id=f"scene.{scene_name}")
        self._light_on = True
        self._last_light_on = monotonic()
        self.log(
            f"ENCIENDE LUCES [{scene_key}] from {origin}",
            level=level,
            log=LOGGER,
        )
        # Store scene to enable looping
        self._last_scene = scene_key

    def _reset_inactivity_timer(self, new_wait: Optional[int] = None):
        if self._handler_turn_off_lights is not None:
            self.cancel_timer(self._handler_turn_off_lights)
            self._handler_turn_off_lights = None
            if new_wait is None:
                self.log(
                    f"Reset wait counter from switch",
                    level=EVENT_LOG_LEVEL,
                    log=LOGGER,
                )
        if new_wait is not None:
            self.log(
                f"Set timer of {new_wait} s from deactivated switch",
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
                self._last_light_on = monotonic()
            self._light_on = True
        elif is_off and old == "on":
            if self._light_on:
                self.log(
                    "UNSYNCED OFF LIGHT (stored as on)",
                    level="ERROR",
                    log=LOGGER,
                )
            self._light_on = False
        elif not is_on and not is_off:
            self.log(
                f"Unavailable LIGHT? {new} (stored as {old})", log=LOGGER,
            )
        else:
            self._light_on = is_on

    def _switch_event(self, _event, event_data, *_args, **_kwargs):
        """
        Listener to manual press on Hue dimmer switch (for manual usage)

        Usually 2 events are received: 'X_click' and 'X_click_up',

        When ON/OFF buttons are used, motion lights are disabled for some time.
        """
        new = RWL_BUTTONS[event_data["event"]]
        if new.endswith("_up"):
            # Ignore button release
            return

        ts_now = monotonic()
        delta = ts_now - self._last_switch_press
        self._last_switch_press = ts_now
        self.log(
            f"MANUAL SWITCH -> {new} (delta_T={delta:.2f}s)",
            level=EVENT_LOG_LEVEL,
            log=LOGGER,
        )

        if new == "1_click":
            # Turn on, no motion control for some time
            if self._motion_light_enabled:
                self._motion_light_enabled = False
                self._motion_on = False
                self._reset_light_enabler(self._max_switch_delay())
                self._reset_inactivity_timer()
            # Turn on light with "kitchen_energy"
            self._turn_lights_on("switch", SCENE_ENERGY)

        elif new == "4_click":
            # Turn off, no motion control for some time
            if self._motion_light_enabled:
                self._motion_light_enabled = False
                self._motion_on = False
                self._reset_light_enabler(DELAY_TO_RE_ENABLE_MOTION_CONTROL)
                self._reset_inactivity_timer()
            # Turn off light
            self._turn_lights_off(manual=True, transition=2)

        elif new == "2_click":
            # Turn on, no motion control for some time
            if self._motion_light_enabled:
                self._motion_light_enabled = False
                self._motion_on = False
                self._reset_light_enabler(self._max_switch_delay())
                self._reset_inactivity_timer()

            # Rotate through scenes
            idx = (SCENE_ROTATION[self._last_scene] + 1) % len(SCENE_ROTATION)
            next_scene = next(
                filter(lambda x: x[1] == idx, SCENE_ROTATION.items())
            )[0]
            self._turn_lights_on("switch_loop", next_scene)

        elif new == "3_hold":
            # Turn off, but enable motion control
            self._turn_lights_off(manual=True, transition=0)
            self._enable_motion_lights()

    def _motion_detected(self, entity, _attribute, old, new, _kwargs):
        """
        Listener to motion sensor changes.

        * New activated motion sensor turns on lights, if motion lights enabled
        * Each activated motion sensor resets the wait timer, if previously set
        * Last deactivated sensor sets a new wait timer to turn off lights.
        """
        if new is None:
            self.log(
                f"Motion sensor disappeared: {entity} -> from {old} to {new}",
                level="WARNING",
                log=LOGGER,
            )
            return

        activated = new == "on"
        if not self._motion_light_enabled:
            if activated and self._light_on:
                # reset wait for enable automatic control (4x mult)
                self._reset_light_enabler(4 * self._get_current_delay())
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
            self._reset_inactivity_timer()
            if not self._light_on:
                self._turn_lights_on(entity)

        elif self._motion_on and not activated and not any_active:
            self._motion_on = False
            # wait some time before turning lights off
            self._reset_inactivity_timer(
                new_wait=self._get_current_delay()
            )
        else:
            self._motion_on = any_active
            if activated:
                self._reset_inactivity_timer()

    def _no_motion_for_long_time(self, *_args, **_kwargs):
        """Listener to main motion sensor being off a long time."""
        light_st = self.get_state(LIGHT_GROUP)
        self._light_on = light_st == "on"

        if not self._light_on:
            return

        now = monotonic()
        self.log(
            f"NO MOTION FOR A LONG TIME (since {self._last_light_on:.0f} s)-> "
            f"{self._motion_states} / {self._motion_on}. "
            f"Handler off={self._handler_turn_off_lights}",
            # level=EVENT_LOG_LEVEL,
            log=LOGGER,
        )
        if (
            (now - self._last_light_on > MAX_DELAY_MOTION_OFF - 1)
            and (now - self._last_switch_press > self._max_switch_delay())
        ) or (
            self._handler_turn_off_lights is None
        ):
            # Safety turn off
            self.log(
                f"TURN OFF LIGHTS AFTER NO MOTION FOR A LONG TIME",
                level="ERROR",
                log=LOGGER,
            )
            self._turn_lights_off()
