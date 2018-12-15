# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant

This little app is a not too simple alarm clock,
which simulates a fast dawn with Hue lights,
while waking up the home cinema system,
waiting for the start of the broadcast of La Cafetera radio program to
start playing it (or, if the alarm is at a different time of
the typical emmision time, it just play the last published episode).

For doing that, it talks directly with Kodi (or Mopidy, without any add-on)
through its JSONRPC API, which has to run a specific Kodi Add-On:
    `plugin.audio.lacafetera`

"""
import appdaemon.plugins.hass.hassapi as hass
import datetime as dt
from dateutil.parser import parse
import pytz
import requests


LOG_LEVEL = 'INFO'

# Defaults para La Cafetera Alarm Clock:
MEDIA_PLAYER = 'media_player.dormitorio'
DEFAULT_SOURCE = 'La Cafetera de Radiocable'
MIN_VOLUME = 1
DEFAULT_MAX_VOLUME_MOPIDY = 60
DEFAULT_DURATION_VOLUME_RAMP = 120
DEFAULT_DURATION = 1.2  # h
DEFAULT_EMISION_TIME = "08:30:00"
TZ = 'CET'
DEFAULT_MIN_POSPONER = 9
MAX_WAIT_TIME = dt.timedelta(minutes=10)
STEP_RETRYING_SEC = 20
DEFAULT_WARM_UP_TIME_DELTA = 25  # s
MIN_INTERVAL_BETWEEN_EPS = dt.timedelta(hours=8)
MASK_URL_STREAM_MOPIDY = "http://api.spreaker.com/listen/episode/{}/http"
TELEGRAM_INLINE_KEYBOARD_ALARMCLOCK = [
    [('A la ducha!', '/ducha'), ('Un poquito +', '/posponer'),
     ('OFF', '/despertadoroff')]]
WEEKDAYS_DICT = {'mon': 0, 'tue': 1, 'wed': 2,
                 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}

SUNRISE_PHASES = [
    {'brightness': 4, 'xy_color': [0.6051, 0.282], 'rgb_color': (62, 16, 17)},
    {'brightness': 30, 'xy_color': [0.672, 0.327], 'rgb_color': (183, 66, 0)},
    {'brightness': 60, 'xy_color': [0.629, 0.353], 'rgb_color': (224, 105, 19)},
    {'brightness': 147, 'xy_color': [0.533, 0.421], 'rgb_color': (255, 175, 53)},
    {'brightness': 196, 'xy_color': [0.4872, 0.4201], 'rgb_color': (255, 191, 92)},
    {'brightness': 222, 'xy_color': [0.4587, 0.4103], 'rgb_color': (255, 199, 117)},
    {'brightness': 254, 'xy_color': [0.449, 0.4078], 'rgb_color': (255, 203, 124)}]


def get_info_last_ep(limit=1):
    """Extrae la información del último (o 'n-último')
    episodio disponible de La Cafetera de Radiocable.com"""
    base_url_v2 = 'https://api.spreaker.com/v2/'
    cafetera_showid = 1060718
    duration = None
    mask_url = base_url_v2 + 'shows/' + str(cafetera_showid) \
        + '/episodes?limit=' + str(limit)
    r = requests.get(mask_url)
    if r.ok:
        data = r.json()
        if ('response' in data) and ('items' in data['response']):
            episode = data['response']['items'][-1]
            published = parse(episode['published_at']).replace(
                tzinfo=pytz.UTC).astimezone(
                pytz.timezone(TZ)).replace(tzinfo=None)
            is_live = episode['type'] == 'LIVE'
            if not is_live:
                duration = dt.timedelta(seconds=episode['duration'] / 1000)
            return True, {'published': published,
                          'is_live': is_live,
                          'duration': duration,
                          'episode': episode}
        return False, data
    return False, None


def is_last_episode_ready_for_play(now):
    """Comprueba si hay un nuevo episodio disponible de La Cafetera.

    :param now: appdaemon datetime.now()
    :return: (play_now, info_last_episode)
    :rtype: tuple(bool, dict)
    """
    est_today = dt.datetime.combine(now.date(),
                                    parse(DEFAULT_EMISION_TIME).time())
    ok, info = get_info_last_ep()
    if ok:
        if (info['is_live'] or
                (now - info['published'] < MIN_INTERVAL_BETWEEN_EPS) or
                (now + MAX_WAIT_TIME < est_today) or
                (now - MAX_WAIT_TIME > est_today)):
            # Reproducir YA
            return True, info
        else:
            # Esperar un poco más a que empiece
            return False, info
    # Network error?
    return False, None


def _make_notification_episode(ep_info):
    """Crea los datos para la notificación de alarma,
    con información del episodio de La Cafetera a reproducir."""
    message = ("La Cafetera [{}]: {}\n(Publicado: {})"
               .format(ep_info['episode']['title'],
                       'LIVE' if ep_info['is_live'] else 'RECORDED',
                       ep_info['published']))
    img_url = ep_info['episode']['image_url']
    title = "Comienza el día en positivo!"
    return title, message, img_url


def _weekday(str_wday):
    str_wday = str_wday.lower().rstrip().lstrip()
    if str_wday in WEEKDAYS_DICT:
        return WEEKDAYS_DICT[str_wday]
    print('Error parsing weekday: "{}" -> mon,tue,wed,thu,fri,sat,sun'
          .format(str_wday))
    return -1


# noinspection PyClassHasNoInit
class AlarmClock(hass.Hass):
    """App for run a complex morning alarm.

    With sunrise light simulation and launching of a Kodi add-on,
    after waking up the home-cinema system,
    or a Modipy instance with a streaming audio."""

    _alarm_on = False
    _alarm_time_input = None
    _warm_up_time_input = None
    _warm_up_boolean = None
    _special_alarm_input = None
    _delta_time_postponer_sec = None
    _warm_up_time_delta = None
    _max_volume = None
    _volume_ramp_sec = None
    _weekdays_alarm = None
    _weekdays_alarm_condition = None
    _notifier = None
    _transit_time = None
    _phases_sunrise = []
    _lights_alarm = None

    _room_select = None
    _manual_trigger = None
    _selected_player = None
    _target_sensor = None

    _media_player_sonos = None

    _next_alarm = None
    _next_warm_up = None
    _next_special_alarm = None
    _handle_alarm = None
    _handle_warm_up = None
    _handle_special_alarm = None

    _last_trigger = None
    _in_alarm_mode = False
    _handler_turnoff = None

    def initialize(self):
        """AppDaemon required method for app init."""
        self._alarm_on = (self.get_state(
            self.args.get('input_boolean_alarm_on')) == 'on')
        self.listen_state(self.master_switch,
                          self.args.get('input_boolean_alarm_on'))

        self._alarm_time_input = self.args.get('alarm_time')
        self._warm_up_time_input = self.args.get('warm_up_time')
        self._warm_up_boolean = self.args.get('warm_up_boolean')
        self._special_alarm_input = self.args.get('special_alarm_datetime')

        self._delta_time_postponer_sec = int(
            self.args.get('postponer_minutos', DEFAULT_MIN_POSPONER)) * 60
        self._max_volume = int(
            self.args.get('max_volume', DEFAULT_MAX_VOLUME_MOPIDY))
        self._volume_ramp_sec = int(
            self.args.get('duration_volume_ramp_sec',
                          DEFAULT_DURATION_VOLUME_RAMP))
        self._weekdays_alarm = [_weekday(d) for d in self.args.get(
            'alarmdays', 'mon,tue,wed,thu,fri').split(',') if _weekday(d) >= 0]
        self._weekdays_alarm_condition = self.args.get('alarmdays_condition')
        self._warm_up_time_delta = dt.timedelta(
            seconds=int(self.args.get('warm_up_time_delta_s',
                                      DEFAULT_WARM_UP_TIME_DELTA)))

        self.listen_state(self.alarm_time_change, self._alarm_time_input)
        self.listen_state(self.warm_up_time_change, self._warm_up_time_input)
        self.listen_state(self.warm_up_time_change, self._warm_up_boolean)
        self.listen_state(self.special_alarm_time_change,
                          self._special_alarm_input)

        # Audio Source selection:
        self._selected_player = DEFAULT_SOURCE
        self._room_select = self.args.get('room_select', None)
        if self._room_select is not None:
            self._selected_player = self.get_state(self._room_select)
            self.listen_state(self.change_player, self._room_select)

        self._media_player_sonos = MEDIA_PLAYER
        self._target_sensor = self.config['chatid_sensor']

        # Trigger for last episode and boolean for play status
        self._manual_trigger = self.args.get('manual_trigger', None)
        if self._manual_trigger is not None:
            self.listen_state(self.manual_triggering, self._manual_trigger)

        # Listen to ios/telegram notification actions:
        self.listen_event(
            self.postpone_secuencia_despertador, 'postponer_despertador')
        self._notifier = self.config['notifier'].replace('.', '/')

        self._lights_alarm = self.args.get('lights_alarm', None)
        total_duration = int(self.args.get('sunrise_duration', 60))
        if not self._phases_sunrise:
            self._phases_sunrise = SUNRISE_PHASES.copy()
        self._transit_time = total_duration // len(self._phases_sunrise) + 1

        self._set_new_alarm_time()
        self._set_new_warm_up_time()
        self._set_new_special_alarm_datetime()
        if self._next_alarm is not None and self._next_warm_up is not None:
            self.log('INIT WITH ALARM AT: {:%H:%M:%S}, WARM UP AT {:%H:%M:%S},'
                     ' NEXT SPECIAL: {} ({})'
                     .format(self._next_alarm, self._next_warm_up,
                             self._next_special_alarm, self._selected_player),
                     LOG_LEVEL)

    def turn_on_morning_services(self, kwargs):
        """Turn ON the water boiler and so on in the morning."""
        self.call_service('switch/turn_on',
                          entity_id="switch.calentador,switch.bomba_circ_acs")
        if 'delta_to_repeat' in kwargs:
            self.run_in(self.turn_on_morning_services,
                        kwargs['delta_to_repeat'])

    def _make_ios_notification_episode(self, ep_info, use_ep_info):
        """Crea los datos para la notificación de alarma para iOS."""
        if use_ep_info:
            title, message, img_url = _make_notification_episode(ep_info)
            return {"title": title, "message": message,
                    "data": {
                        "push": {
                            "badge": 0,
                            "sound": "US-EN-Morgan-Freeman-Good-Morning.wav",
                            "category": "alarmclock"
                        },
                        "attachment": {"url": img_url}}}
        else:
            return {"title": "Comienza el día en positivo",
                    "message": "Reproduciendo {}".format(
                        self._selected_player),
                    "data": {"push": {
                        "badge": 0,
                        "sound": "US-EN-Morgan-Freeman-Good-Morning.wav",
                        "category": "alarmclock"}
                    }}

    def _make_telegram_notification_episode(self, ep_info, use_ep_info):
        """Crea los datos para la notificación de alarma para telegram."""
        if use_ep_info:
            title, message, img_url = _make_notification_episode(ep_info)
        else:
            title = "Comienza el día en positivo"
            message = "Reproduciendo {}".format(self._selected_player)
            img_url = None
        title = '*{}*'.format(title)
        if img_url is not None:
            message += "\n{}\n".format(img_url)
        data_msg = {"title": title, "message": message,
                    # "keyboard": TELEGRAM_KEYBOARD_ALARMCLOCK,
                    "inline_keyboard": TELEGRAM_INLINE_KEYBOARD_ALARMCLOCK,
                    "disable_notification": False}
        return data_msg

    def notify_alarmclock(self, ep_info, use_ep_info):
        """Send notification with episode info."""
        self.call_service(
            'telegram_bot/send_message',
            target=int(self.get_state(self._target_sensor)),
            **self._make_telegram_notification_episode(ep_info, use_ep_info))
        self.call_service(
            self._notifier.replace('.', '/'),
            **self._make_ios_notification_episode(ep_info, use_ep_info))

    # noinspection PyUnusedLocal
    def change_player(self, entity, attribute, old, new, kwargs):
        """Change player."""
        self.log('CHANGE PLAYER from {} to {}'
                 .format(self._selected_player, new))
        self._selected_player = new

    # noinspection PyUnusedLocal
    def turn_off_alarm_clock(self, *args):
        """Stop current play when turning off the input_boolean."""
        if self._in_alarm_mode:
            if self.get_state(self._media_player_sonos) == 'playing':
                self.call_service('media_player/turn_off',
                                  entity_id=self._media_player_sonos)
            # self.turn_on_bedroom_speakers({'off': True})
            if self._manual_trigger is not None:
                self._last_trigger = None
                self.set_state(self._manual_trigger, state='off')
            self.log('TURN_OFF SONOS')
        else:
            self.log('TURN_OFF ALARM CLOCK, BUT ALREADY OFF?')
        if self._handler_turnoff is not None:
            self.cancel_timer(self._handler_turnoff)
            self._handler_turnoff = None
        self._in_alarm_mode = False

    # noinspection PyUnusedLocal
    def master_switch(self, entity, attribute, old, new, kwargs):
        """Start reproduction manually."""
        self._alarm_on = (new == 'on')
        self.log('MASTER SWITCH BOOLEAN CHANGED from {} to {}'
                 .format(old, new))

    # noinspection PyUnusedLocal
    def manual_triggering(self, entity, attribute, old, new, kwargs):
        """Start reproduction manually."""
        self.log('MANUAL_TRIGGERING BOOLEAN CHANGED from {} to {}'
                 .format(old, new))
        # Manual triggering
        if (new == 'on') and ((self._last_trigger is None)
                              or ((dt.datetime.now() - self._last_trigger)
                                  .total_seconds() > 30)):
            _ready, ep_info = is_last_episode_ready_for_play(self.datetime())
            use_ep_info = self.run_in_sonos(ep_info)
            # Notification:
            self.notify_alarmclock(ep_info, use_ep_info)
        # Manual stop after at least 10 sec
        elif ((new == 'off') and (old == 'on')
              and (self._last_trigger is not None) and
                  ((dt.datetime.now() - self._last_trigger)
                   .total_seconds() > 10)):
            # Stop if it's playing
            self.log('TRIGGER_STOP (last trigger at {})'
                     .format(self._last_trigger))
            self.turn_off_alarm_clock()

    # noinspection PyUnusedLocal
    def alarm_time_change(self, entity, attribute, old, new, kwargs):
        """Re-schedule next alarm when alarm time sliders change."""
        self._set_new_alarm_time()
        self.log('CHANGING ALARM TIME TO: {:%H:%M:%S}'
                 .format(self._next_alarm), LOG_LEVEL)

    # noinspection PyUnusedLocal
    def warm_up_time_change(self, entity, attribute, old, new, kwargs):
        """Re-schedule next alarm when alarm time sliders change."""
        self._set_new_warm_up_time()

    # noinspection PyUnusedLocal
    def special_alarm_time_change(self, entity, attribute, old, new, kwargs):
        """Re-schedule next alarm when alarm time sliders change."""
        self._set_new_special_alarm_datetime()
        self.log('CHANGING SPECIAL ALARM TIME TO: {:%d/%m/%y %H:%M:%S}'
                 .format(self._next_special_alarm), LOG_LEVEL)

    def _set_new_alarm_time(self):
        if self._handle_alarm is not None:
            self.cancel_timer(self._handle_alarm)
        alarm_time = self.get_state(self._alarm_time_input, attribute="all")
        if alarm_time is None or alarm_time['state'] == 'unknown':
            self._next_alarm = None
            return

        time_alarm = dt.datetime.now().replace(
            hour=alarm_time['attributes']['hour'],
            minute=alarm_time['attributes']['minute'],
            second=0, microsecond=0)

        self._next_alarm = time_alarm  # - self._warm_up_time_delta
        self._handle_alarm = self.run_daily(
            self.run_alarm, self._next_alarm.time())

    # noinspection PyUnusedLocal
    def _set_new_warm_up_time(self, *args):
        # _handle_special_alarm
        if self._handle_warm_up is not None:
            self.cancel_timer(self._handle_warm_up)
        alarm_time = self.get_state(self._warm_up_time_input, attribute="all")
        trigger_warm_up = self.get_state(self._warm_up_boolean) == 'on'

        if (not trigger_warm_up
                or (alarm_time is None)
                or (alarm_time['state'] == 'unknown')):
            self._next_warm_up = None
            self.log('Remove WARM UP TIME', LOG_LEVEL)
            return

        time_alarm = dt.datetime.now().replace(
            hour=alarm_time['attributes']['hour'],
            minute=alarm_time['attributes']['minute'],
            second=0, microsecond=0)

        self._next_warm_up = time_alarm  # - self._warm_up_time_delta
        self._handle_warm_up = self.run_daily(
            self.run_warm_up, self._next_warm_up.time())
        self.log('CHANGING WARM UP TIME TO: {:%H:%M:%S}'
                 .format(self._next_warm_up), LOG_LEVEL)

    # noinspection PyUnusedLocal
    def _set_new_special_alarm_datetime(self, *args):
        if self._handle_special_alarm is not None:
            self.cancel_timer(self._handle_special_alarm)
        alarm_time = self.get_state(self._special_alarm_input, attribute="all")
        if alarm_time is None or alarm_time['state'] == 'unknown':
            self._next_special_alarm = None
            return

        time_alarm = dt.datetime.now().replace(
            year=alarm_time['attributes']['year'],
            month=alarm_time['attributes']['month'],
            day=alarm_time['attributes']['day'],
            hour=alarm_time['attributes']['hour'],
            minute=alarm_time['attributes']['minute'],
            second=0, microsecond=0)

        self._next_special_alarm = time_alarm  # - self._warm_up_time_delta
        try:
            self._handle_special_alarm = self.run_at(
                self.trigger_service_in_alarm, self._next_special_alarm)
        except ValueError:
            self.log("ERROR setting special alarm at {}!".format(time_alarm))
            self._handle_special_alarm = None

    def _set_sunrise_phase(self, *args_runin):
        self.log('SET_SUNRISE_PHASE: XY={xy_color}, '
                 'BRIGHT={brightness}, TRANSITION={transition}'
                 .format(**args_runin[0]), 'DEBUG')
        if self._in_alarm_mode:
            self.call_service('light/turn_on', **args_runin[0])

    # noinspection PyUnusedLocal
    def turn_on_lights_as_sunrise(self, *args):
        """Turn on the lights with a sunrise simulation.

         (done with multiple slow transitions)"""
        # self.log('RUN_SUNRISE')
        self.call_service(
            'light/turn_off', entity_id=self._lights_alarm, transition=0)
        self.call_service(
            'light/turn_on', entity_id=self._lights_alarm, transition=1,
            xy_color=self._phases_sunrise[0]['xy_color'], brightness=1)
        run_in = 2
        for phase in self._phases_sunrise:
            # noinspection PyTypeChecker
            xy_color, brightness = phase['xy_color'], phase['brightness']
            self.run_in(self._set_sunrise_phase, run_in,
                        entity_id=self._lights_alarm, xy_color=xy_color,
                        transition=self._transit_time, brightness=brightness)
            run_in += self._transit_time + 1

    # noinspection PyUnusedLocal
    def increase_volume(self, *args):
        """Recursive method to increase the playback volume until max."""
        self.log("INCREASE VOLUME GRADUALLY")
        repeat = True
        if self._in_alarm_mode and self._last_trigger is not None:
            delta_sec = (dt.datetime.now()
                         - self._last_trigger).total_seconds()
            if delta_sec > self._volume_ramp_sec:
                volume_set = self._max_volume
                repeat = False
            else:
                volume_set = int(max(
                    MIN_VOLUME,
                    (delta_sec / self._volume_ramp_sec)
                    * self._max_volume)) / 100.
            self.call_service('media_player/volume_set',
                              entity_id=self._media_player_sonos,
                              volume_level=volume_set)
        else:
            repeat = False
        if repeat:
            self.run_in(self.increase_volume, 10)

    def run_in_sonos(self, ep_info):
        """Play stream in Sonos."""
        use_ep_info = False
        self.call_service('media_player/volume_set',
                          entity_id=self._media_player_sonos,
                          volume_level=0)
        if self._selected_player == DEFAULT_SOURCE:
            self.call_service(
                'media_player/play_media',
                entity_id=self._media_player_sonos,
                media_content_type='music',
                media_content_id='http://api.spreaker.com/listen/'
                                 'show/1060718/episode/latest/shoutcast.mp3')
            self.log('TRIGGER_START with ep_info --> {}'.format(ep_info))
            use_ep_info = True
        else:
            self.call_service('media_player/select_source',
                              entity_id=self._media_player_sonos,
                              source=self._selected_player)

        self.call_service('media_player/volume_set',
                          entity_id=self._media_player_sonos,
                          volume_level=.01)

        self._in_alarm_mode = True
        self._last_trigger = dt.datetime.now()
        self.run_in(self.increase_volume, 5)
        return use_ep_info

    # noinspection PyUnusedLocal
    def trigger_service_in_alarm(self, *args):
        """Launch alarm secuence.

        Launch if ready, or set itself to retry in the short future."""
        # Check if alarm is ready to launch
        if self._alarm_on and not self._in_alarm_mode:
            alarm_ready, alarm_info = is_last_episode_ready_for_play(
                self.datetime())
            if alarm_ready:
                # self.turn_on_morning_services(dict(delta_to_repeat=30))
                use_ep_info = self.run_in_sonos(alarm_info)
                self.turn_on_lights_as_sunrise()
                # Notification:
                self.notify_alarmclock(alarm_info, use_ep_info)
                self.set_state(self._manual_trigger, state='on')
                if alarm_info['duration'] is not None:
                    duration = alarm_info['duration'].total_seconds() + 20
                    self._handler_turnoff = self.run_in(
                        self.turn_off_alarm_clock, int(duration))
                    self.log('ALARM RUNNING NOW. AUTO STANDBY PROGRAMMED '
                             'IN {:.0f} SECONDS'.format(duration), LOG_LEVEL)
                else:
                    self._handler_turnoff = self.listen_state(
                        self.turn_off_alarm_clock, self._media_player_sonos,
                        new="off", duration=20)
            else:
                self.log('POSTPONE ALARM', LOG_LEVEL)
                self.run_in(self.trigger_service_in_alarm, STEP_RETRYING_SEC)

    def is_working_day(self):
        if ((not self._weekdays_alarm_condition
             or self.get_state(self._weekdays_alarm_condition) == 'on') and
                self.datetime().weekday() in self._weekdays_alarm):
            return True
        return False

    # noinspection PyUnusedLocal
    def run_alarm(self, *args):
        """Run the alarm main secuence: prepare, trigger & schedule next"""
        if not self.get_state(self._manual_trigger) == 'on':
            # self.set_state(self._manual_trigger, state='off')
            if self._alarm_on and self.is_working_day():
                self.trigger_service_in_alarm()
            else:
                self.log('ALARM CLOCK NOT TRIGGERED TODAY '
                         '(weekday={}, alarm weekdays={})'
                         .format(self.datetime().weekday(),
                                 self._weekdays_alarm))
        else:
            self.log('Alarm clock is running manually, no auto-triggering now')

    # noinspection PyUnusedLocal
    def run_warm_up(self, *args):
        """Run the warm up sequence"""
        if self.is_working_day():
            self.turn_on_morning_services(dict(delta_to_repeat=10))
            self.log('Warm up trigger')
        else:
            self.run_in(self.turn_on_morning_services, 1800,
                        delta_to_repeat=10)
            self.log('Warm up trigger in 1800 s')

    # noinspection PyUnusedLocal
    def postpone_secuencia_despertador(self, *args):
        """Botón de postponer alarma X min"""
        self.turn_off_alarm_clock()
        self.call_service('light/turn_off',
                          entity_id=self._lights_alarm, transition=1)
        self.run_in(self.trigger_service_in_alarm,
                    self._delta_time_postponer_sec)
        self.log('Postponiendo alarma {:.1f} minutos...'
                 .format(self._delta_time_postponer_sec / 60.))
