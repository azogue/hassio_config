# -*- coding: utf-8 -*-
"""
Appdaemon app for motion + switch control of light in a room.
"""
from time import monotonic
from typing import Any, Dict, Optional, Tuple

import appdaemon.plugins.hass.hassapi as hass

LOGGER = "motion_log"
EVENT_LOG_LEVEL = "DEBUG"

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


# noinspection PyClassHasNoInit
class HueSwitchAndMotionControl(hass.Hass):
    """
    App to automate lights in a room with:
    - One or more motion sensors
    - A Hue Dimmer Switch for manual control, with priority over automatic.
    """

    _main_constrain: str
    _light_group: str
    _scene_rotation: Dict[str, int]
    _default_scene: str
    _scenes: Dict[str, Tuple[Dict[str, Any], int]] = {}
    _time_windows: Dict[str, Tuple[str, str]]
    _delay_re_enable_motion_control: int
    _max_delay_motion_off: int

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
        remote_event = self.args.get("remote_event", "deconz_event")
        remote_event_filter = self.args.get("remote_event_filter", {})
        motion_sensors = self.args.get("motion_sensors", [])
        self._light_group = self.args.get("light_group", "light.cocina")
        self._main_constrain = self.args.get("toggle_automation")
        self._delay_re_enable_motion_control = int(
            self.args.get("delay_re_enable_motion_control", 120)
        )
        self._max_delay_motion_off = int(
            self.args.get("max_delay_motion_off", 900)
        )

        self._scene_rotation = {
            scene_key: i
            for i, scene_key in enumerate(self.args.get("rotate_scene_order"))
        }
        _schedule_config = self.args.get("scene_schedule")
        self.log(
            f"[DEBUG] APP INIT with schedule_config {_schedule_config}",
            level="WARNING",
            log=LOGGER,
        )

        self._default_scene = self.args.get("default_scene")
        self._scenes = {}
        self._time_windows = {}
        for scene_key, scene_data in self.args.get("scene_schedule").items():
            self._time_windows[scene_key] = (
                scene_data.get("from", "00:00:00"),
                scene_data.get("to", "00:00:00"),
            )
            self._scenes[scene_key] = (
                scene_data["turn_on_service_call"],
                scene_data["wait_to_turn_off"],
            )

        light_st = self.get_state(self._light_group)
        self._light_on = light_st == "on"
        self._last_switch_press = 0.0
        self._last_scene = self._default_scene

        self._motion_states = {}
        for sensor in motion_sensors:
            self._motion_states[sensor] = self.get_state(sensor) == "on"
            self.listen_state(
                self._motion_detected,
                sensor,
                constrain_input_boolean=self._main_constrain,
            )
        self._motion_on = any(self._motion_states.values())
        self._last_light_on = 0.0 if not self._motion_on else monotonic()
        self._motion_light_enabled = True

        self.listen_state(self._light_changed, self._light_group)
        self.listen_event(
            self._switch_event, remote_event, **remote_event_filter
        )
        # Add listener to check light off after a long time
        self.listen_state(
            self._no_motion_for_long_time,
            motion_sensors[0],
            new="off",
            duration=self._max_delay_motion_off,
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
            "light/turn_off", entity_id=self._light_group, transition=transition
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
        scene_key = None
        for scene_key, (from_str, to_str) in self._time_windows.items():
            if self.now_is_between(from_str, to_str):
                return scene_key

        return scene_key

    def _get_current_delay(self):
        return self._scenes[self._select_scene()][1]

    def _max_switch_delay(self):
        return 5 * self._get_current_delay()

    def _turn_lights_on(self, origin: str, scene_key: Optional[str] = None):
        level = "INFO"
        if scene_key is None:
            level = "WARNING"
            scene_key = self._select_scene()

        turn_on_data = self._scenes[scene_key][0]
        self.call_service(
            turn_on_data["service"], **turn_on_data["service_data"]
        )
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
            # Turn on light with "default_scene"
            self._turn_lights_on("switch", self._default_scene)

        elif new == "2_click":
            # Turn on, no motion control for some time
            if self._motion_light_enabled:
                self._motion_light_enabled = False
                self._motion_on = False
                self._reset_light_enabler(self._max_switch_delay())
                self._reset_inactivity_timer()

            # Rotate through scenes
            idx = (
                self._scene_rotation[self._last_scene] + 1
            ) % len(self._scene_rotation)
            next_scene = next(
                filter(lambda x: x[1] == idx, self._scene_rotation.items())
            )[0]
            self._turn_lights_on("switch_loop", next_scene)

        elif new == "3_hold":
            # Turn off, but enable motion control
            self._turn_lights_off(manual=True, transition=0)
            self._enable_motion_lights()

        elif new == "4_click":
            # Turn off, no motion control for some time
            if self._motion_light_enabled:
                self._motion_light_enabled = False
                self._motion_on = False
                self._reset_light_enabler(self._delay_re_enable_motion_control)
                self._reset_inactivity_timer()
            # Turn off light
            self._turn_lights_off(manual=True, transition=2)

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
        light_st = self.get_state(self._light_group)
        self._light_on = light_st == "on"

        if not self._light_on:
            return

        now = monotonic()
        self.log(
            f"NO MOTION FOR A LONG TIME (since {self._last_light_on:.0f} s)-> "
            f"{self._motion_states} / {self._motion_on}. "
            f"Handler off={self._handler_turn_off_lights}",
            log=LOGGER,
        )
        if (
            (now - self._last_light_on > self._max_delay_motion_off - 1)
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
