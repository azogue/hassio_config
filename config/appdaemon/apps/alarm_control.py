# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant

Event listener for actions triggered from a Telegram Bot chat
or from iOS notification actions.

Harcoded custom logic for controlling HA with feedback from these actions.

"""
import datetime as dt
import json
import subprocess
from random import randrange
import re
from time import time

import appdaemon.plugins.hass.hassapi as hass
from fuzzywuzzy.process import extractOne
# import paramiko


LOG_LEVEL = 'DEBUG'

BINARY_SENSORS = '''binary_sensor.database_ok
binary_sensor.dormitorio_online
binary_sensor.electricity_high_cost_interval
binary_sensor.email_online
binary_sensor.esp32_ener_online
binary_sensor.internet_online
binary_sensor.ios_online
binary_sensor.kodi_online
binary_sensor.local_pir,
binary_sensor.motioncam_office,
binary_sensor.motioncam_salon,
binary_sensor.motioncam_terraza,
binary_sensor.pushbullet_online
binary_sensor.router_on
binary_sensor.sensor_galeria_online
binary_sensor.sensor_kitchen_mov1
binary_sensor.sensor_kitchen_online
binary_sensor.sensor_livingroom_mov1,
binary_sensor.sensor_livingroom_online
binary_sensor.sensor_office_mov1,
binary_sensor.sensor_office_online
binary_sensor.sensor_terraza_mov1,
binary_sensor.sensor_terraza_online
binary_sensor.services_notok,
binary_sensor.telegram_online
binary_sensor.workday_sensor'''

CAMERAS = '''camera.iegeek_hd
camera.kmoon_ipcam100
camera.sricam_360'''
MOTION_SENSORS = ','.join('''binary_sensor.internet_online
binary_sensor.router_on
binary_sensor.local_pir
binary_sensor.motioncam_office
binary_sensor.motioncam_salon
binary_sensor.motioncam_terraza
binary_sensor.sensor_kitchen_mov1
binary_sensor.sensor_livingroom_mov1
binary_sensor.sensor_office_mov1
binary_sensor.sensor_terraza_mov1'''.splitlines())

# LEVELS = [None, 'disarmed', 'armed_home', 'armed_night', 'armed_away']
ALARM_MODE_LEVELS = {'disarmed': 0,
                     'armed_home': 1,
                     'armed_night': 2,
                     'armed_away': 3}
AUTOMATIONS = {
    'automation.apagado_automatico_de_termo_acs': 'armed_away',

    'automation.encendido_automatico_de_cam_salon': 'armed_night',
    'automation.apagado_de_cam_salon_en_kodi_play_nocturno': 'armed_night',
    'automation.apagado_de_tv_si_encendida_y_kodi_en_idle__10_min': 'armed_night',

    'automation.sync_tira_tv_con_tira_sofa': 'armed_away',
    'automation.brillo_salon': 'armed_away',
    'automation.tono_salon': 'armed_away',
    'automation.salon_select_scene': 'armed_away',
    'automation.notify_sunset': 'armed_away',
    'automation.buenas_noches': 'armed_away',
    'automation.carmen_llega_al_hospital': 'armed_away',
    'automation.carmen_sale_del_hospital': 'armed_away',
    'automation.encendido_de_tv_si_apagada_y_kodi_play': 'armed_away',
    'automation.encendido_luces_dormitorio': 'armed_away',

    'automation.aviso_de_sensor_mqtt_offline': 'armed_away',
    # 'automation.botvac_error_notification': None,
    # 'automation.new_bt_device_notifier': None,
    # 'automation.start_homeassistant': None,
    # 'automation.update_notifications': None,
}

ALARM_PANEL = 'alarm_control_panel.alarma'
SENSOR_CURRENT_LEVEL = 'sensor.current_alarm_level'
SENSOR_CURRENT_LEVEL_ATTRS = {
    "unit_of_measurement": 'risk',
    "homebridge_hidden": True,
    "icon": 'mdi:home-alert',
    "friendly_name": 'Nivel de Alerta'}


# noinspection PyClassHasNoInit
class AlarmControl(hass.Hass):
    """Alarm Handler."""

    _ha_key = None
    _base_url = None

    _lights_notif = None
    _lights_notif_state = None
    _lights_notif_st_attr = None
    _notifier = None

    _bot_notifier = 'telegram_bot'
    _bot_target = None

    # Alarm state
    _alarm_state = False
    _alarm_triggered = False
    _alarm_mode = None

    _room_cameras = {}
    _motion_sensors = {}
    _motion_states = {}
    _handlers_listen_motion = {}
    _last_risk = 0

    # Configuration
    _rooms = {}

    # HASS entities:
    # _hass_entities = None
    # _hass_entities_plain = None

    # Scheduled tasks
    # _scheduled = {}

    def initialize(self):
        """AppDaemon required method for app init."""
        # Config
        self._ha_key = self.args.get('ha_key')
        self._base_url = self.args.get('base_url')
        self._lights_notif = self.args.get('lights_notif', 'light.cuenco')
        self._notifier = self.config.get('notifier').replace('.', '/')
        self._bot_target = self.args.get('bot_target')
        self._rooms = self.args.get('rooms')

        # Inputs
        self._motion_sensors = {
            ent if ent.startswith('binary_s') else weight.split(',')[0]:
                weight if ent.startswith('binary_s') else int(
                    weight.split(',')[1])
            for room, sensors in self._rooms.items()
            for ent, weight in sensors.items()}

        self._update_motion_states()
        self._room_cameras = {
            r: (list(filter(lambda x: x.startswith('camera'),
                            self._rooms[r].keys()))[0],
                [k if k.startswith('binary_s')
                 else self._rooms[r][k].split(',')[0]
                 for k in s.keys()]) for r, s in self._rooms.items()
            if any([k.startswith('camera') for k in self._rooms[r].keys()])}

        # Master state
        self.listen_state(self.alarm_mode_controller, entity=ALARM_PANEL)
        alarm_state = self.get_state(ALARM_PANEL)
        self._alarm_state = alarm_state != 'disarmed'
        if not self._alarm_state:
            self._alarm_mode = 'disarmed'
        else:
            self.set_alarm_mode(alarm_state)
        self.log(f"Init with alarm_state: {self._alarm_state} "
                 f"[{self._alarm_mode}]; ROOMS: {self._rooms}")
        self.log(f"MOTION: {self._motion_sensors}; "
                 f"CAMERAS: {self._room_cameras}")
        SENSOR_CURRENT_LEVEL_ATTRS["hidden"] = not self._alarm_state
        self._last_risk = self.eval_risk('init')
        self.set_state(SENSOR_CURRENT_LEVEL,
                       state=self._last_risk if self._alarm_state else 0,
                       attributes=SENSOR_CURRENT_LEVEL_ATTRS)

        keyboard = [f'Desarmar:/disarm, Ignorar:/ignorar, +:/init']
        msg = dict(title='*ALARM TEST*',
                   message=f"Mode: {self._alarm_state}",
                   target=self._bot_target,
                   # disable_notification=False,
                   inline_keyboard=keyboard)
        self.call_service('telegram_bot/send_message', **msg)

    def _update_motion_states(self):
        self._motion_states = {
            bs: self.get_state(bs) == 'on' for bs in self._motion_sensors}

    def eval_risk(self, caller):
        self._update_motion_states()
        risk_unit = {bs: self._motion_sensors[bs] if state else 0
                     for bs, state in self._motion_states.items()}
        risk = sum(risk_unit.values())
        self.log(f"[caller: {caller}, ALARM: {self._alarm_state}]. "
                 f"Risk evaluation --> {risk}")
        if self._alarm_state:
            SENSOR_CURRENT_LEVEL_ATTRS["hidden"] = False
            self.set_state(SENSOR_CURRENT_LEVEL, state=risk,
                           attributes=SENSOR_CURRENT_LEVEL_ATTRS)
        return risk

    def disarm_alarm(self):
        self._alarm_state = False
        self._alarm_mode = None
        self._alarm_triggered = False
        # Reset alarm level, and hide it
        SENSOR_CURRENT_LEVEL_ATTRS["hidden"] = True
        self.set_state(SENSOR_CURRENT_LEVEL, state=-1,
                       attributes=SENSOR_CURRENT_LEVEL_ATTRS)

        # Cancel listeners
        for bs, h in self._handlers_listen_motion.items():
            self.cancel_listen_state(h)

        # OFF motion in cams
        # Future: tell to OFF motion sensors in ESP devices
        self.call_service('switch/turn_off',
                          entity_id='switch.motion_detection_sricam_360,'
                                    'switch.motion_detection_iegeek_hd,'
                                    'switch.motion_detection_kmoon_ipcam100')

        # Turn on automations
        self.call_service('automation/turn_on',
                          entity_id=','.join(AUTOMATIONS))

    def set_alarm_mode(self, alarm_mode):
        if self._alarm_state:
            self.log(f"Error in set_alarm_mode[{alarm_mode}], already set: {self._alarm_mode} [triggered: {self._alarm_triggered}]")
            return

        self._alarm_state = True
        self._alarm_triggered = False
        self._alarm_mode = alarm_mode
        self._last_risk = self.eval_risk('panel_change')

        # Reset alarm level, and show it
        SENSOR_CURRENT_LEVEL_ATTRS["hidden"] = False
        self.set_state(SENSOR_CURRENT_LEVEL, state=0,
                       attributes=SENSOR_CURRENT_LEVEL_ATTRS)

        # Turn off automations
        alarm_level = ALARM_MODE_LEVELS[alarm_mode]
        automations_to_turn_off = filter(
            lambda x: ALARM_MODE_LEVELS[AUTOMATIONS[x]] <= alarm_level,
            AUTOMATIONS)
        self.call_service('automation/turn_off',
                          entity_id=','.join(automations_to_turn_off))

        # ON motion in cams
        # Future: tell to ON motion sensors in ESP devices
        self.call_service('switch/turn_on',
                          entity_id='switch.motion_detection_sricam_360,'
                                    'switch.motion_detection_iegeek_hd,'
                                    'switch.motion_detection_kmoon_ipcam100')

        # TODO filter devices, group as rooms with cams
        # self.call_service('switch/turn_on',
        #                   entity_id='switch.motion_detection_sricam_360,switch.motion_detection_iegeek_hd,switch.motion_detection_kmoon_ipcam100')
        self._update_motion_states()
        self._handlers_listen_motion = {
            ent: self.listen_state(
                self.motion_change, entity=ent)
            for ent in self._motion_sensors}

    # noinspection PyUnusedLocal
    def motion_change(self, entity, attribute, old, new, kwargs):
        last_known_state = self._motion_states[entity]
        if last_known_state != (old == 'on'):
            self.log(f"Change error: last known was {last_known_state}, "
                     f"but the change is between {old} and {new} for {entity}")
        self._motion_states[entity] = new == 'on'
        if self._alarm_state:
            new_risk = self.eval_risk(entity)
            self.log(f"[{entity}] Motion change (->{new == 'on'}): "
                     f"Risk: {new_risk} [∆:{new_risk - self._last_risk}]")
            self._last_risk = new_risk

            # Has to trigger the alarm?
            if new_risk > 10 and not self._alarm_triggered:
                self._alarm_triggered = True
                self.call_service('alarm_control_panel/alarm_trigger',
                                  entity_id=ALARM_PANEL)
                self.log(f"ACTIVANDO ALARMA (risk:{new_risk}) --> PANEL:"
                         f"{str(self.get_state(ALARM_PANEL, attribute='all'))}")

            # Assoc camera:
            # assoc_cam_room = list(filter(
            #     lambda x: entity in self._room_cameras[x][1],
            #     self._room_cameras))
            # if assoc_cam_room:
            #     self.log(f"Movimiento con cámara asociada: "
            #              f"{self._room_cameras[assoc_cam_room[0]][0]}")


    # noinspection PyUnusedLocal
    def alarm_mode_controller(self, entity, attribute, old, new, kwargs):
        """Cambia el master switch cuando se utiliza el input_select"""
        self.log('ALARM_MODE_CONTROLLER {} -> {}, attrs: {},{}'.format(old, new, attribute, kwargs))

        if new == 'disarmed':  # Disarm ALL
            self.log(f"DISARMING ALARM: (from '{old}')")
            self.disarm_alarm()

            # ON useful automations
            # OFF motion in cams
            # Future: tell to OFF motion sensors in ESP devices
            # OFF cams

        elif old == 'disarmed':  # going to pending or armed_X
            if new != 'pending':
                self.log(f"SET DIRECT ALARM MODE: '{new}'")
                self.set_alarm_mode(new)
        elif new.startswith('armed_') and new != self._alarm_mode:  # going to armed_X (first time)
            self.log(f"SET ALARM MODE: '{new}'")
            self.set_alarm_mode(new)
        elif new == 'triggered':  # Notify!
            self._alarm_triggered = True
            self.log(f"ALARM TRIGGERED! -> Notify")
            # self.notify("", name='telegram_bot')
            # keyboard = [f'Desarmar:/service_call alarm_control_panel.alarm_disarm {ALARM_PANEL}']
            keyboard = [f'Desarmar:/disarm, Ignorar:/ignorar, +:/init']
            msg = dict(title='*ALARMA*',
                       message=f"Mode: {new} (de {old})",
                       target=self._bot_target,
                       # disable_notification=False,
                       inline_keyboard=keyboard)
            self.call_service('telegram_bot/send_message', **msg)
            # self._alarm_mode = new
        elif new == 'pending' and self._alarm_state:  # pending trigger
            self.log(f"PRE-ALARM MODE in [{self._alarm_mode}]!")
            self._alarm_mode = new
        else:
            self.log(f"UNKNOWN COMBINATION!")
            self._alarm_mode = new

    # TODO bajar persiana si away
    # TODO rooms - sensors assoc --> emulate_motion to record in rooms
    # TODO binary_sensor filter, params, control, etc.
    # TODO Notifications, sirena, etc..
    # TODO Integrate with konnected alarm


