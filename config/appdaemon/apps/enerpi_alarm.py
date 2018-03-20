# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant - current meter PEAK POWER notifications
"""
import datetime as dt
import appdaemon.plugins.hass.hassapi as hass


LOG_LEVEL = 'INFO'
DEFAULT_UPPER_LIMIT_KW = 4
DEFAULT_LOWER_LIMIT_KW = 2
DEFAULT_MIN_TIME_UPPER_SEC = 3
DEFAULT_MIN_TIME_LOWER_SEC = 60
MASK_MSG_MAX_POWER = {"title": "Alto consumo eléctrico!",
                      "message": "Pico de potencia: {} W en {}"}
MASK_MSG_MAX_POWER_RESET = {"title": "Consumo eléctrico: Normal",
                            "message": "Potencia normal desde {}, Pico de potencia: {} W."}


# noinspection PyClassHasNoInit
class EnerpiPeakNotifier(hass.Hass):
    """App for Notifying the power peaks when they are greater than a certain limit, and after that,
    notify when back to normal (lower than another user defined limit)."""

    # Limit Values
    _upper_limit = None
    _min_time_upper = None
    _lower_limit = None
    _min_time_lower = None

    # App user inputs
    # _switch_on_off_app = None --> `constrain_input_boolean`
    _main_power = None
    _notifier = None
    _target_sensor = None
    _camera = None
    _slider_upper_limit = None
    _slider_lower_limit = None

    _alarm_state = False
    _last_trigger = None
    _current_peak = 0

    def initialize(self):
        """AppDaemon required method for app init."""
        self._main_power = self.args.get('control')
        self._notifier = self.config.get('notifier').replace('.', '/')
        self._target_sensor = self.config.get('chatid_sensor')
        self._camera = self.args.get('camera')
        self._min_time_upper = int(self.args.get('min_time_high', DEFAULT_MIN_TIME_UPPER_SEC))
        self._min_time_lower = int(self.args.get('min_time_low', DEFAULT_MIN_TIME_LOWER_SEC))

        # App user inputs
        self._slider_upper_limit = self.args.get('max_power_kw', '')
        self._slider_lower_limit = self.args.get('max_power_kw_reset', '')
        self._upper_limit = DEFAULT_UPPER_LIMIT_KW * 1000
        self._lower_limit = DEFAULT_LOWER_LIMIT_KW * 1000
        if self._slider_upper_limit:
            try:
                self._upper_limit = int(1000 * float(self._slider_upper_limit))
            except ValueError:
                state = self.get_state(self._slider_lower_limit)
                if state:
                    self._upper_limit = int(1000 * float(self.get_state(self._slider_upper_limit)))
                    self.listen_state(self._slider_limit_change, self._slider_upper_limit)
        if self._slider_lower_limit:
            try:
                self._lower_limit = int(1000 * float(self._slider_lower_limit))
            except ValueError:
                state = self.get_state(self._slider_lower_limit)
                if state:
                    self._lower_limit = int(1000 * float(self.get_state(self._slider_lower_limit)))
                    self.listen_state(self._slider_limit_change, self._slider_lower_limit)
        elif self._slider_upper_limit:
            self._lower_limit = self._upper_limit // 2

        # Listen for Main Power changes:
        self.listen_state(self._main_power_change, self._main_power)

        self.log('EnerpiPeakNotifier Initialized. P={}, with P>{} W for {} secs, (low={} W for {} secs). Notify: {}'
                 .format(self._main_power, self._upper_limit, self._min_time_upper,
                         self._lower_limit, self._min_time_lower, self._notifier))

    def _get_notif_data(self, reset_alarm=False):
        time_now = '{:%H:%M:%S}'.format(self._last_trigger) if self._last_trigger is not None else '???'
        if reset_alarm:
            data_msg = MASK_MSG_MAX_POWER_RESET.copy()
            data_msg["message"] = data_msg["message"].format(time_now, self._current_peak)
        else:
            data_msg = MASK_MSG_MAX_POWER.copy()
            data_msg["message"] = data_msg["message"].format(self._current_peak, time_now)
        return data_msg

    def _make_ios_message(self, reset_alarm=False):
        data_msg = self._get_notif_data(reset_alarm)
        if reset_alarm:
            data_msg["data"] = {"push": {"category": "camera", "badge": 0},
                                "entity_id": self._camera}
        else:
            data_msg["data"] = {
                "push": {
                    "category": "camera", "badge": 1,
                    "sound": "US-EN-Morgan-Freeman-Vacate-The-Premises.wav"},
                "entity_id": self._camera}
        return data_msg

    def _make_telegram_message(self, reset_alarm=False):
        data_msg = self._get_notif_data(reset_alarm)
        data_msg["target"] = int(self.get_state(self._target_sensor))
        data_msg["inline_keyboard"] = [[('Luces ON', '/luceson'),
                                 ('Luces OFF', '/lucesoff')],
                                [('Potencia eléctrica', '/enerpi'),
                                 ('Grafs. enerPI', '/enerpitiles')],
                                [('Calentador OFF', '/service_call switch/turn_off switch.calentador')]]
        return data_msg

    # noinspection PyUnusedLocal
    def _slider_limit_change(self, entity, attribute, old, new, kwargs):
        if entity == self._slider_upper_limit:
            self._upper_limit = int(1000 * float(new))
        elif entity == self._slider_lower_limit:
            self._lower_limit = int(1000 * float(new))
        self.log('LIMIT CHANGE FROM "{}" TO "{}" --> upper_limit={} W, lower_limit={} W'
                 .format(old, new, self._upper_limit, self._lower_limit))

    # noinspection PyUnusedLocal
    def _main_power_change(self, entity, attribute, old, new, kwargs):
        """Power Peak ALARM logic control."""
        now = dt.datetime.now()
        try:
            new = int(float(new))
        except ValueError:
            return

        # Update peak
        if new > self._current_peak:
            self._current_peak = new
        if not self._alarm_state and (new > self._upper_limit):  # Pre-Alarm state, before trigger
            # Prealarm
            if self._last_trigger is None:  # Start power peak event
                self.log('New power peak event at {} with P={} W'.format(now, new), level=LOG_LEVEL)
                self._last_trigger = now
            elif (now - self._last_trigger).total_seconds() > self._min_time_upper:
                # TRIGGER ALARM
                alarm_msg = self._make_ios_message()
                self.log('TRIGGER ALARM with msg={}'
                         .format(alarm_msg), level=LOG_LEVEL)
                self.call_service(self._notifier, **alarm_msg)
                self.call_service('telegram_bot/send_message',
                                  **self._make_telegram_message())
                self._alarm_state = True
                self._last_trigger = now
            # else:  # wait some more time (this is the same power peak event, waiting min time to trigger alarm)
            #     pass
        elif self._alarm_state:  # Alarm state, waiting for reset
            if new < self._lower_limit:
                # self.log('IN ALARM MODE!!')
                if (now - self._last_trigger).total_seconds() > self._min_time_lower:
                    self.log('RESET ALARM MODE at {}'.format(now), level=LOG_LEVEL)
                    # RESET ALARM
                    self.call_service(
                        self._notifier,
                        **self._make_ios_message(reset_alarm=True))
                    self.call_service(
                        'telegram_bot/send_message',
                        **self._make_telegram_message(reset_alarm=True))
                    self._alarm_state = False
                    self._last_trigger = None
                    self._current_peak = 0
            else:
                self._last_trigger = now
        elif (self._last_trigger is not None) and ((now - self._last_trigger).total_seconds() > self._min_time_lower):
            # Normal operation, reset last trigger if no more in min_time_lower
                self.log('RESET LAST TRIGGER (was in {})'.format(self._last_trigger), level=LOG_LEVEL)
                self._last_trigger = None
