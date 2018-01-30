# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant

This little app controls some hue lights for turning them ON with motion detection,
only under some custom circunstances, like the media player is not running,
or there aren't any more lights in 'on' state in the room.

"""
import appdaemon.appapi as appapi


LOG_LEVEL = 'INFO'


# noinspection PyClassHasNoInit
class MotionLights(appapi.AppDaemon):
    """App for control lights with a motion sensor."""

    _pir = None
    _motion_light_timeout = None
    _lights_motion = None
    _lights_check_off = None
    _media_player = None
    _extra_constrain_input_boolean = None

    _handle_motion_on = None
    _handle_motion_off = None

    _motion_lights_running = False
    _extra_condition = True
    _media_player_active = False
    _lights_motion_active = None

    def initialize(self):
        """AppDaemon required method for app init."""
        conf_data = dict(self.config['AppDaemon'])
        pir = self.args.get('pir', None)
        self._extra_constrain_input_boolean = self.args.get(
            'constrain_input_boolean_2', None)
        motion_light_timeout_slider = self.args.get(
            'motion_light_timeout', None)
        self._lights_motion = self.args.get('lights_motion', '')
        self._lights_check_off = [l for l in self.args.get(
            'lights_check_off', '').split(',') if len(l) > 0]
        self._media_player = conf_data.get('media_player', None)

        if pir and motion_light_timeout_slider and self._lights_motion:
            self._pir = pir
            # Motion Lights States
            self._lights_motion_active = {}
            self._read_light_motion_states(set_listen_state=True)
            self.run_minutely(self._read_light_motion_states, None)
            # for l in self._lights_motion.split(','):
            #     self._lights_motion_active[l] = self.get_state(l) == 'on'
            #     self.listen_state(self._light_motion_state, l)
            # Light Timeout
            if motion_light_timeout_slider.startswith('input_number'):
                self._motion_light_timeout = int(
                    round(float(self.get_state(motion_light_timeout_slider))))
                self.listen_state(
                    self._set_motion_timeout, motion_light_timeout_slider)
            else:
                self._motion_light_timeout = int(
                    round(float(motion_light_timeout_slider)))
            self._handle_motion_on = self.listen_state(
                self.turn_on_motion_lights, self._pir, new="on")
            self._handle_motion_off = self.listen_state(
                self.turn_off_motion_lights, self._pir,
                new="off", duration=self._motion_light_timeout)
            # Media player dependency
            if self._media_player is not None:
                self._media_player_active = self.get_state(
                    self._media_player) == 'playing'
                self.listen_state(
                    self._media_player_state_ch, self._media_player)
                self.log('MotionLightsConstrain media player "{}" (PIR={})'
                         .format(self._media_player, self._pir))

            # Extra dependency (inverse logic) --> GENERAL ALARM ON
            if self._extra_constrain_input_boolean is not None:
                self._extra_condition = self.get_state(
                    self._extra_constrain_input_boolean) == 'off'
                self.listen_state(
                    self._extra_switch_change,
                    self._extra_constrain_input_boolean)
                self.log('MotionLightsConstrain extra "{}" (extra_cond now={})'
                         .format(self._extra_constrain_input_boolean,
                                 self._extra_condition))
            self.log('MotionLights [{}] with motion in "{}", '
                     'with timeout={} s, check_off={}. ---> ACTIVE'
                     .format(self._lights_motion, self._pir,
                             self._motion_light_timeout,
                             self._lights_check_off))
        else:
            self.log('No se inicializa MotionLights, '
                     'faltan parámetros (req: {})'
                     .format('motion_light_timeout, lights_motion, pir'),
                     level='ERROR')

    # noinspection PyUnusedLocal
    def _media_player_state_ch(self, entity, attribute, old, new, kwargs):
        self._media_player_active = new == 'playing'

    # noinspection PyUnusedLocal
    def _extra_switch_change(self, entity, attribute, old, new, kwargs):
        self.log('Extra switch condition change: {} from {} to {}'
                 .format(entity, old, new))
        self._extra_condition = new == 'off'

    # noinspection PyUnusedLocal
    def _set_motion_timeout(self, entity, attribute, old, new, kwargs):
        new_timeout = int(round(float(new)))
        if new_timeout != self._motion_light_timeout:
            self._motion_light_timeout = new_timeout
            if self._handle_motion_off is not None:
                self.log('Cancelling {}'.format(self._handle_motion_off))
                self.cancel_listen_state(self._handle_motion_off)
            self._handle_motion_off = self.listen_state(
                self.turn_off_motion_lights, self._pir,
                new="off", duration=self._motion_light_timeout)
            self.log('Se establece nuevo timeout para MotionLights: {} segs'
                     .format(self._motion_light_timeout))

    # noinspection PyUnusedLocal
    def _read_light_motion_states(self, set_listen_state=False, **kwargs):
        bkp = self._lights_motion_active.copy()
        if not self._motion_lights_running:
            for l in self._lights_motion.split(','):
                self._lights_motion_active[l] = self.get_state(l) == 'on'
                if set_listen_state:
                    self.listen_state(self._light_motion_state, l)
        elif any(filter(lambda x: x is False,
                        self._lights_motion_active.values())):
            self.log('MOTION LIGHTS OFF (some lights were turn off manually)'
                     ' --> {}'.format(self._lights_motion_active))
            self._motion_lights_running = False
        if set_listen_state or (bkp != self._lights_motion_active):
            self.log('UPDATE light_motion_states from {} to {}'
                     .format(bkp, self._lights_motion_active,
                             set_listen_state))

    # noinspection PyUnusedLocal
    def _light_motion_state(self, entity, attribute, old, new, kwargs):
        self._lights_motion_active[entity] = new == 'on'

    def _lights_are_off(self, include_motion_lights=True):
        other_lights_are_off = ((self._lights_check_off is None)
                                or all([(self.get_state(l) == 'off')
                                        or (self.get_state(l) is None)
                                        for l in self._lights_check_off]))
        if include_motion_lights:
            return other_lights_are_off and not any(
                self._lights_motion_active.values())
        return other_lights_are_off

    # noinspection PyUnusedLocal
    def turn_on_motion_lights(self, entity, attribute, old, new, kwargs):
        """Method for turning on the motion-controlled lights."""
        if (not self._motion_lights_running and
                self._lights_are_off(include_motion_lights=True) and
                self._extra_condition and not self._media_player_active):
            self._motion_lights_running = True
            self.log('TURN_ON MOTION_LIGHTS ({}), with timeout: {} sec. '
                     'lights_motion: {}'
                     .format(self._lights_motion, self._motion_light_timeout,
                             self._lights_motion_active.values()),
                     LOG_LEVEL)
            self.call_service("light/turn_on", entity_id=self._lights_motion,
                              color_temp=300, brightness=200, transition=0)

    # noinspection PyUnusedLocal
    def turn_off_motion_lights(self, entity, attribute, old, new, kwargs):
        """Method for turning off the motion-controlled lights
        after some time without any movement."""
        if self._motion_lights_running and \
                self._extra_condition and not self._media_player_active:
            if self._lights_are_off(include_motion_lights=False):
                self.log('TURNING_OFF MOTION_LIGHTS, id={}, old={}, new={}'
                         .format(entity, old, new), LOG_LEVEL)
                self.call_service("light/turn_off",
                                  entity_id=self._lights_motion, transition=1)
            else:
                self.log('NO TURN_OFF MOTION_LIGHTS '
                         '(other lights in the room are ON={})'
                         .format([self.get_state(l)
                                  for l in self._lights_check_off]), LOG_LEVEL)
            self._motion_lights_running = False
