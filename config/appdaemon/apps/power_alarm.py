# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant -
current meter PEAK POWER notifications
"""
import datetime as dt
from enum import IntEnum

import appdaemon.plugins.hass.hassapi as hass


LOG_LEVEL = "INFO"
LOG_LEVEL_ALERT = "WARNING"
LOGGER = "special_event_log"

COEF_CRITICAL_LIMIT = 1.1  # 10% over limit
MIN_TIME_TURN_OFF_AC = 60  # secs

# Big power consumers
BIG_CONSUMER_1_CLIMATE = "switch.ac_dry_contact"
BIG_CONSUMER_1_LABEL = "aire acondicionado"
BIG_CONSUMER_2 = "switch.calentador"
BIG_CONSUMER_2_LABEL = "calentador"

_IOS_SOUND_POWER_PEAK = "US-EN-Morgan-Freeman-Vacate-The-Premises.wav"


class TypeNotif(IntEnum):
    """
    Handler for different kinds of power notifications.

    Used to centralize push message construction.
    """

    ALERT_OFF = 0
    ALERT_ON = 1
    ALERT_CRITICAL = 2

    def make_ios_push_data(self, data_msg: dict) -> dict:
        if self.value == self.ALERT_CRITICAL:
            push_data = {
                "category": "powerpeak",
                "badge": 10,
                "sound": _IOS_SOUND_POWER_PEAK,
                "critical": 1,
                "volume": 1.0,
                "thread-id": "power-peak-group",
            }
        elif self.value == self.ALERT_ON:
            push_data = {
                "category": "powerpeak",
                "thread-id": "power-peak-group",
                "badge": 1,
                "critical": 1,
                "sound": _IOS_SOUND_POWER_PEAK,
            }
        else:
            push_data = {
                "category": "confirm",
                "thread-id": "power-peak-group",
                "sound": _IOS_SOUND_POWER_PEAK,
                "badge": 0,
            }

        data_msg["data"] = {"push": push_data}
        return data_msg

    def make_telegram_push_data(self, data_msg: dict, target: int) -> dict:
        data_msg["target"] = int(self.get_state(self._target_sensor))
        data_msg["target"] = target
        data_msg["disable_notification"] = self.value == self.ALERT_OFF
        data_msg["inline_keyboard"] = [
            [("Luces ON", "/luceson"), ("Luces OFF", "/lucesoff")],
            [
                ("Potencia eléctrica", "/enerpi"),
                ("Grafs. enerPI", "/enerpitiles"),
            ],
            [
                (
                    "Calentador OFF",
                    "/service_call switch/turn_off switch.calentador",
                ),
                (
                    "AC OFF",
                    "/service_call switch/turn_off switch.ac_dry_contact",
                ),
            ],
        ]

        return data_msg

    def make_notification_message(
        self,
        current_peak,
        last_trigger,
        alarm_start,
        devices_off="",
        pow_instant=0.0,
        pow_sustained=0.0,
    ) -> dict:
        if self.value == self.ALERT_CRITICAL:
            return {
                "title": "¡El automático está a punto de saltar!",
                "message": (
                    f"Apagando {devices_off} para intentar evitar "
                    "la sobrecarga eléctrica."
                ),
            }

        time_now = (
            "{:%H:%M:%S}".format(last_trigger)
            if last_trigger is not None
            else "???"
        )
        if self.value == self.ALERT_ON:
            data_msg = {
                "title": "Alto consumo eléctrico!",
                "message": (
                    f"Peak: {current_peak} W en {time_now}. "
                    f"Ahora {pow_instant} W ({pow_sustained} sostenidos)"
                ),
            }
            data_msg["message"] = data_msg["message"].format(
                self._current_peak, time_now, pow_instant, pow_sustained
            )

        else:
            duration_min = (
                dt.datetime.now() - alarm_start
            ).total_seconds() / 60.0
            data_msg = {
                "title": "Consumo eléctrico: Normal",
                "message": (
                    f"Potencia normal desde {time_now}, "
                    f"Pico de potencia: {current_peak} W. "
                    f"Alerta iniciada hace {duration_min:.1f} min."
                ),
            }
        return data_msg


# noinspection PyClassHasNoInit
class PeakNotifier(hass.Hass):
    """
    App to notify power peaks (when they are greater than a certain limit),
    and after that, notify when back to normal (< lower limit).
    """

    # Limit Values
    _max_peak: float
    _upper_limit: float
    _lower_limit: float
    _min_time_high: int
    _min_time_low: int

    # App user inputs
    _main_power: str
    _main_power_peak: str
    _notifier: str
    _target_sensor: str

    _alarm_state: bool = False
    _critical_alarm_state: bool = False
    _last_trigger = None
    _alarm_start = None
    _turn_off_measure_taken = False
    _current_peak = 0

    def initialize(self):
        """AppDaemon required method for app init."""
        self._main_power = self.args.get("sustained_power")
        self._main_power_peak = self.args.get("instant_power")
        self._notifier = self.config.get("notifier").replace(".", "/")
        self._target_sensor = self.config.get("chatid_sensor")

        # Power limits
        self._upper_limit = float(self.args.get("max_power_kw")) * 1000.0
        self._lower_limit = float(self.args.get("max_power_kw_reset")) * 1000.0
        self._min_time_high = int(self.args.get("min_time_high"))
        self._min_time_low = int(self.args.get("min_time_low"))
        # TODO implement _max_peak over _instant_power
        self._max_peak = float(self.args.get("max_power_peak_kw")) * 1000.0

        # Listen for Main Power changes:
        self.listen_state(self.main_power_change, self._main_power)

        self.log(
            f"PeakNotifier Initialized. P={self._main_power}, "
            f"with P>{self._upper_limit} W for {self._min_time_high} secs, "
            f"(low={self._lower_limit} W for {self._min_time_low} secs). "
            f"Notify: {self._notifier}.",
            level=LOG_LEVEL,
            log=LOGGER,
        )

    def notify_alert(self, type_notif: TypeNotif, data: dict):
        ios_alarm_msg = type_notif.make_ios_push_data(data.copy())
        tlg_alarm_msg = type_notif.make_telegram_push_data(
            data.copy(), target=int(self.get_state(self._target_sensor)),
        )
        self.call_service(self._notifier, **ios_alarm_msg)
        self.call_service("telegram_bot/send_message", **tlg_alarm_msg)

    # noinspection PyUnusedLocal
    def peak_power_change(self, entity, attribute, old, new, kwargs):
        """Power Peak ALARM logic control."""
        try:
            new = int(float(new))
        except ValueError:
            return

        # Update peak
        if new > self._upper_limit and new > self._current_peak:
            self._current_peak = new

    # noinspection PyUnusedLocal
    def main_power_change(self, entity, attribute, old, new, kwargs):
        """Sustained Power ALARM logic control."""
        try:
            new = int(float(new))
        except ValueError:
            return

        now = dt.datetime.now()
        if not self._alarm_state and (new > self._upper_limit):
            if new > self._current_peak:
                self._current_peak = new
            # Pre-Alarm state, before trigger
            if self._last_trigger is None:
                # Start power peak event
                self.log(
                    "New power peak event at {} with P={} W".format(now, new),
                    level=LOG_LEVEL,
                    log=LOGGER,
                )
                self._last_trigger = now
            elif (
                now - self._last_trigger
            ).total_seconds() > self._min_time_high:
                # TRIGGER ALARM
                self._alarm_start = now
                self._turn_off_measure_taken = False
                type_notif = TypeNotif.ALERT_ON
                data = type_notif.make_notification_data(
                    self._current_peak,
                    self._last_trigger,
                    self._alarm_start,
                    pow_instant=self.get_state(self._main_power_peak),
                    pow_sustained=new,
                )
                self.log(
                    f"TRIGGER ALARM with msg={data}",
                    level=LOG_LEVEL_ALERT,
                    log=LOGGER,
                )
                self.notify_alert(type_notif, data)
                self._alarm_state = True
                self._critical_alarm_state = False

                self._last_trigger = now
            # else:  # wait some more time
            # (this is the same power peak event,
            # waiting min time to trigger alarm)
            #     pass
        elif self._alarm_state:  # Alarm state, waiting for reset
            if new > self._current_peak:
                self._current_peak = new

            if (
                not self._turn_off_measure_taken
                and new > self._upper_limit * COEF_CRITICAL_LIMIT
            ):
                self.log(
                    "ENABLE CRITICAL ALARM with {} W".format(new),
                    level=LOG_LEVEL_ALERT,
                    log=LOGGER,
                )
                self._critical_alarm_state = True
            elif new < self._lower_limit:
                if (
                    now - self._last_trigger
                ).total_seconds() > self._min_time_low:
                    # RESET ALARM
                    type_notif = TypeNotif.ALERT_OFF
                    data = type_notif.make_notification_data(
                        self._current_peak,
                        self._last_trigger,
                        self._alarm_start,
                    )
                    self.log(
                        "RESET ALARM MODE at {}".format(now),
                        level=LOG_LEVEL,
                        log=LOGGER,
                    )
                    self.notify_alert(type_notif, data)

                    self._alarm_state = False
                    self._critical_alarm_state = False
                    self._last_trigger = None
                    self._alarm_start = None
                    self._turn_off_measure_taken = False
                    self._current_peak = 0
            elif (
                not self._turn_off_measure_taken
                and self._critical_alarm_state
                and new < self._upper_limit
            ):
                self.log(
                    "DISABLE CRITICAL ALARM (now {} W)".format(new),
                    level=LOG_LEVEL_ALERT,
                    log=LOGGER,
                )
                self._critical_alarm_state = False

            elif (
                not self._turn_off_measure_taken
                and self._critical_alarm_state
                and (
                    (now - self._alarm_start).total_seconds()
                    > MIN_TIME_TURN_OFF_AC
                )
            ):
                # Turn off AC if AC + heater are ON
                self._turn_off_measure_taken = True
                self._critical_alarm_state = False

                devices_turning_off = ""
                if self.get_state(BIG_CONSUMER_1_CLIMATE) == "on":
                    devices_turning_off = BIG_CONSUMER_1_LABEL
                    self.call_service("climate/turn_off", entity_id="all")
                elif self.get_state(BIG_CONSUMER_2) == "on":
                    devices_turning_off = BIG_CONSUMER_2_LABEL
                    self.call_service(
                        "switch/turn_off", entity_id=BIG_CONSUMER_2
                    )

                if devices_turning_off:
                    # Notification of devices turned off
                    self.log(
                        f"CRITICAL ACTION: Turn off '{devices_turning_off}'",
                        level="ERROR",
                        log=LOGGER,
                    )
                    type_notif = TypeNotif.ALERT_CRITICAL
                    data = type_notif.make_notification_data(
                        self._current_peak,
                        self._last_trigger,
                        self._alarm_start,
                        devices_off=devices_turning_off,
                        pow_instant=self.get_state(self._main_power_peak),
                        pow_sustained=new,
                    )
                    self.notify_alert(type_notif, data)

                self._last_trigger = now
            else:
                self._last_trigger = now
        elif (self._last_trigger is not None) and (
            (now - self._last_trigger).total_seconds() > self._min_time_low
        ):
            # Normal operation, reset last trigger if no more in min_time_lower
            self.log(
                "RESET LAST TRIGGER (was in {})".format(self._last_trigger),
                level=LOG_LEVEL,
                log=LOGGER,
            )
            self._last_trigger = None
            self._current_peak = 0
