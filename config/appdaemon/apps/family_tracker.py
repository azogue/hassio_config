# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant

Event listener for actions triggered from a Telegram Bot chat
or from iOS notification actions.

Harcoded custom logic for controlling HA with feedback from these actions.

"""
from dateutil.parser import parse
import pytz
import appdaemon.plugins.hass.hassapi as hass


# DELAY_TO_SET_DEFAULT_TARGET = 1800  # sec
DELAY_TO_SET_DEFAULT_TARGET = 120  # sec
TZ = 'Europe/Madrid'

# noinspection PyClassHasNoInit
class FamilyTracker(hass.Hass):
    """Family Tracker."""

    _tracking_state = None
    _telegram_targets = None
    _notifier = None
    _timer_update_target = None
    _base_url = None
    _anybody_home = None

    def initialize(self):
        """AppDaemon required method for app init."""
        self.log(f"bot_chatids: {self.args.get('bot_chatids')}, "
                 f"notifier: {self.config.get('notifier')}")
        _chatids = [int(x) for x in self.args.get('bot_chatids').split(',')]
        self._notifier = self.config.get('notifier').replace('.', '/')
        self._base_url = self.args.get('base_url').replace('.', '/')
        self._anybody_home = False

        # Get home group
        home_group = self.args.get('home_group', 'group.family')

        # Get default chat_id for home
        default_chat_id = self.args.get('bot_group_target')
        self._telegram_targets = {"default": ('Casa', default_chat_id)}

        people_track = self.args.get('people', {})
        # self.log("people_track: {}".format(people_track))

        # Get devices to track:
        _devs_track = self.get_state(
            home_group, attribute='attributes')['entity_id']

        # Get tracking states:
        self._tracking_state = {}
        for dev in _devs_track:
            target = None
            name = self.friendly_name(dev)
            tracking_st = [self.get_state(dev),
                           parse(self.get_state(dev, attribute='last_changed')).replace(
                tzinfo=pytz.UTC).astimezone(
                pytz.timezone(TZ)).replace(tzinfo=None)]
            self._tracking_state[dev] = tracking_st

            # Listen for state changes:
            self.listen_state(self.track_zone_ch, dev, old="home", duration=60)
            self.listen_state(self.track_zone_ch, dev, new="home", duration=2)

            # Get details for each device/group:
            if dev in people_track:
                # Get telegram target
                if 'chat_id_idx' in people_track[dev]:
                    target = _chatids[people_track[dev]['chat_id_idx']]
                # Listen for extra devices (input_booleans):
                if 'extra_tracker' in people_track[dev]:
                    dev_extra = people_track[dev]['extra_tracker']
                    extra_tracking_st = [
                        self.get_state(dev_extra),
                        parse(self.get_state(dev, attribute='last_changed')).replace(
                tzinfo=pytz.UTC).astimezone(
                pytz.timezone(TZ)).replace(tzinfo=None)]
                    self._telegram_targets[dev_extra] = (name, target)
                    self._tracking_state[dev_extra] = extra_tracking_st
                    self.listen_state(self.track_zone_ch, dev_extra)
            self._telegram_targets[dev] = (name, target)

        # Process (and write globals) who is at home
        self._who_is_at_home(False)

    def _make_notifications(self, exiting_home, telegram_target):
        if exiting_home:
            # Salida de casa:
            title = "¡Vuelve pronto!"
            message = "¿Apagamos luces o encendemos alarma?"
            cat = "away"
            keyboard = ['Activar alarma:/armado',
                        'Activar vigilancia:/vigilancia',
                        'Apagar luces:/lucesoff, +:/init']
        else:
            # Llegada:
            title = "Welcome home!"
            message = "¿Qué puedo hacer por ti?"
            cat = "inhome"
            keyboard = ['Welcome:/llegada',
                        'Welcome + TV:/llegadatv',
                        'Ignorar:/ignorar, +:/init']

        # Service calls payloads
        data_ios = {
            "title": title,
            "message": message,
            "data": {"push": {"badge": 1 if exiting_home else 0,
                              "category": cat}}
        }
        data_telegram = {
            "title": '*{}*'.format(title),
            "message": message + '\n[Go home]({})'.format(self._base_url),
            "inline_keyboard": keyboard,
            "target": telegram_target,
            "disable_notification": True,
        }
        return data_ios, data_telegram

    def _who_is_at_home(self, zone_changed):
        if self._timer_update_target is not None:
            self.cancel_timer(self._timer_update_target)
            self._timer_update_target = None

        people, new_target = {}, None
        for dev, (st, last_ch) in self._tracking_state.items():
            at_home = (st == 'home') or (st == 'on')
            person, target = self._telegram_targets[dev]
            if person not in people:
                people[person] = at_home, last_ch, dev
                if at_home:
                    new_target = target
            elif last_ch > people[person][1]:
                people[person] = at_home, last_ch, dev

        # Set default chat_id and people_home
        people_home = {k: v for k, v in people.items() if v[0]}
        new_anybody_home = len(people_home) > 0
        if not new_anybody_home and zone_changed:
            # Set last person exiting the house (at least for some time)
            last_dev = list(sorted(people.values(), key=lambda x: x[2]))[-1][2]
            _last_person, new_target = self._telegram_targets[last_dev]
            self._timer_update_target = self.run_in(
                self._who_is_at_home, DELAY_TO_SET_DEFAULT_TARGET,
                zone_changed=False)
        elif not new_anybody_home or len(people_home) > 1:
            new_target = self._telegram_targets["default"][1]
        else:
            self.log("WHO IS AT HOME? people: {}, zone_changed:{}, target:{}"
                       .format(people, zone_changed, new_target))

        if new_target is None:
            return

        self.call_service(
            'python_script/set_telegram_chatid_sensor', chat_id=new_target)

        # Todo entradas - salidas de personas individuales
        if new_anybody_home != self._anybody_home:
            data_ios, data_telegram = self._make_notifications(
                not new_anybody_home, new_target)
            # self.log('IOS NOTIF: {}'.format(data_ios))
            # self.log('TELEGRAM NOTIF: {}'.format(data_telegram))
            self.call_service(self._notifier, **data_ios)
            self.call_service('telegram_bot/send_message',
                              **data_telegram)
            self._anybody_home = new_anybody_home

    # noinspection PyUnusedLocal
    def track_zone_ch(self, entity, attribute, old, new, kwargs):
        """State change listener."""
        last_st, last_ch = self._tracking_state[entity]
        self._tracking_state[entity] = [new, self.datetime()]

        self.log(f"DEBUG Actual tracking state: {self._tracking_state}")

        # Process changes
        self._who_is_at_home(True)

        if last_st != old:
            self.log('!!BAD TRACKING_STATE_CHANGE "{}" from "{}" [!="{}"'
                     ', changed at {}] to "{}"'
                     .format(entity, old, last_st, last_ch, new))
        else:
            self.log('TRACKING_STATE_CHANGE "{}" from "{}" [{}] to "{}"'
                     .format(entity, old, last_ch, new))
