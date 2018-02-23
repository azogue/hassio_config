"""
Support for MQTT cover devices.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/cover.mqttcoverswitch/
"""
import asyncio
from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.core import callback
import homeassistant.components.mqtt as mqtt
from homeassistant.components.cover import (
    CoverDevice, SUPPORT_OPEN, SUPPORT_CLOSE, SUPPORT_STOP,
    SUPPORT_SET_POSITION, ATTR_CURRENT_POSITION, ATTR_POSITION)
from homeassistant.const import CONF_NAME, CONF_OPTIMISTIC
from homeassistant.components.mqtt import (
    CONF_AVAILABILITY_TOPIC, CONF_PAYLOAD_AVAILABLE,
    CONF_PAYLOAD_NOT_AVAILABLE, CONF_QOS, CONF_RETAIN,
    valid_publish_topic, valid_subscribe_topic, MqttAvailability)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.restore_state import async_get_last_state
from homeassistant.util.dt import utcnow

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['mqtt']

CONF_DELAY_FULL_OPEN = 'delay_full_open'
DEFAULT_DELAY_FULL_OPEN = 10  # seconds

CONF_STATE_SWITCH_OPEN_TOPIC = 'state_switch_open_topic'
CONF_STATE_SWITCH_CLOSE_TOPIC = 'state_switch_close_topic'
CONF_COMMAND_SWITCH_OPEN_TOPIC = 'command_switch_open_topic'
CONF_COMMAND_SWITCH_CLOSE_TOPIC = 'command_switch_close_topic'

CONF_PAYLOAD_OPEN = 'payload_open'
CONF_PAYLOAD_CLOSE = 'payload_close'
CONF_PAYLOAD_STOP_OPEN = 'payload_stop_open'
CONF_PAYLOAD_STOP_CLOSE = 'payload_stop_close'

DEFAULT_NAME = 'MQTT Cover Switch'
DEFAULT_PAYLOAD_OPEN = 'on'
DEFAULT_PAYLOAD_CLOSE = 'on'
DEFAULT_PAYLOAD_STOP = 'off'
DEFAULT_OPTIMISTIC = True
DEFAULT_RETAIN = False
DEFAULT_QOS = 0

OPEN_CLOSE_FEATURES = (SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP)

PLATFORM_SCHEMA = mqtt.MQTT_BASE_PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_STATE_SWITCH_OPEN_TOPIC): valid_subscribe_topic,
    vol.Required(CONF_STATE_SWITCH_CLOSE_TOPIC): valid_subscribe_topic,
    vol.Required(CONF_COMMAND_SWITCH_OPEN_TOPIC): valid_publish_topic,
    vol.Required(CONF_COMMAND_SWITCH_CLOSE_TOPIC): valid_publish_topic,
    vol.Optional(CONF_PAYLOAD_OPEN, default=DEFAULT_PAYLOAD_OPEN): cv.string,
    vol.Optional(CONF_PAYLOAD_STOP_OPEN,
                 default=DEFAULT_PAYLOAD_STOP): cv.string,
    vol.Optional(CONF_PAYLOAD_CLOSE,
                 default=DEFAULT_PAYLOAD_CLOSE): cv.string,
    vol.Optional(CONF_PAYLOAD_STOP_CLOSE,
                 default=DEFAULT_PAYLOAD_STOP): cv.string,
    vol.Optional(CONF_DELAY_FULL_OPEN, default=DEFAULT_DELAY_FULL_OPEN):
        vol.All(vol.Coerce(float),
                vol.Range(min=0.1, max=120, min_included=False)),
    vol.Optional(CONF_OPTIMISTIC, default=DEFAULT_OPTIMISTIC): cv.boolean,
    vol.Optional(CONF_QOS, default=DEFAULT_QOS): int,
    vol.Optional(CONF_RETAIN, default=DEFAULT_RETAIN): cv.boolean,
}).extend(mqtt.MQTT_AVAILABILITY_SCHEMA.schema)


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the MQTT Cover."""
    if discovery_info is not None:
        config = PLATFORM_SCHEMA(discovery_info)

    async_add_devices([MqttCoverSwitch(
        config.get(CONF_NAME),
        config.get(CONF_STATE_SWITCH_OPEN_TOPIC),
        config.get(CONF_STATE_SWITCH_CLOSE_TOPIC),
        config.get(CONF_COMMAND_SWITCH_OPEN_TOPIC),
        config.get(CONF_COMMAND_SWITCH_CLOSE_TOPIC),
        config.get(CONF_PAYLOAD_OPEN),
        config.get(CONF_PAYLOAD_STOP_OPEN),
        config.get(CONF_PAYLOAD_CLOSE),
        config.get(CONF_PAYLOAD_STOP_CLOSE),
        config.get(CONF_DELAY_FULL_OPEN),
        config.get(CONF_OPTIMISTIC),
        config.get(CONF_AVAILABILITY_TOPIC),
        config.get(CONF_PAYLOAD_AVAILABLE),
        config.get(CONF_PAYLOAD_NOT_AVAILABLE),
        config.get(CONF_QOS),
        config.get(CONF_RETAIN)
    )])


class MqttCoverSwitch(MqttAvailability, CoverDevice):
    """Representation of a cover that can be controlled using MQTT."""

    def __init__(self, name, state_switch_open_topic, state_switch_close_topic,
                 command_switch_open_topic, command_switch_close_topic,
                 payload_open, payload_stop_open,
                 payload_close, payload_stop_close,
                 delay_full_open, optimistic, availability_topic,
                 payload_available, payload_not_available, qos, retain):
        """Initialize the cover."""
        super().__init__(availability_topic, qos, payload_available,
                         payload_not_available)
        self._name = name
        self._state = None
        self._position = None
        self._tic_last_action = None
        self._last_action_is_opening = False
        self._stop_checker = None
        self._delay_full_open = delay_full_open

        self._state_sw_open = False
        self._state_sw_close = False

        self._state_switch_open_topic = state_switch_open_topic
        self._state_switch_close_topic = state_switch_close_topic

        self._command_switch_open_topic = command_switch_open_topic
        self._command_switch_close_topic = command_switch_close_topic

        self._qos = qos
        self._payload_open = payload_open
        self._payload_close = payload_close
        self._payload_stop_open = payload_stop_open
        self._payload_stop_close = payload_stop_close

        self._retain = retain
        self._optimistic = optimistic or state_switch_open_topic is None

    @property
    def is_opening(self):
        """Return if the cover is opening or not."""
        if self._state_sw_open and self._state_sw_close:
            _LOGGER.error("Opening and closing at the same time may "
                          "result in an electrical shortage!")
            yield from self.async_stop_cover(is_safe_stop=True)
            _is_opening = False
        elif self._state_sw_open:
            _is_opening = True
        else:
            _is_opening = False
        _LOGGER.warning("is_opening?: {}".format(_is_opening))
        return _is_opening

    @property
    def is_open(self):
        """Return if the cover is open or not."""
        if self._position is not None and self._position > 99:
            return True
        return False

    @property
    def is_closing(self):
        """Return if the cover is closing or not."""
        if self._state_sw_open and self._state_sw_close:
            _LOGGER.error("Opening and closing at the same time may "
                          "result in an electrical shortage!")
            yield from self.async_stop_cover(is_safe_stop=True)
            return False
        elif self._state_sw_close:
            return True
        else:
            return False

    @property
    def is_closed(self):
        """Return if the cover is closed or not."""
        if self._position is not None and self._position < 1:
            return True
        return False

    @property
    def current_cover_position(self):
        """Return current position of cover.

        None is unknown, 0 is closed, 100 is fully open.
        """
        return self._position

    @asyncio.coroutine
    def async_added_to_hass(self):
        """Subscribe MQTT events."""
        yield from super().async_added_to_hass()

        last_state = yield from async_get_last_state(self.hass, self.entity_id)
        if last_state is not None:
            data = last_state.as_dict()
            if ATTR_CURRENT_POSITION in data['attributes']:
                self._position = data['attributes'][ATTR_CURRENT_POSITION]
                _LOGGER.info("Got last position for cover %s: %d",
                             self.name, self._position)

        @callback
        def state_message_received(topic, payload, qos):
            """Handle new MQTT state messages."""
            if topic == self._state_switch_open_topic:
                if payload == self._payload_open:
                    self._state_sw_open = True
                else:
                    self._state_sw_open = False
            elif topic == self._state_switch_close_topic:
                if payload == self._payload_close:
                    self._state_sw_close = True
                else:
                    self._state_sw_close = False
            else:
                _LOGGER.warning("Payload is not True or False: %s:%s",
                                topic, payload)
                return

            self.async_schedule_update_ha_state()

        @callback
        def availability_message_received(topic, payload, qos):
            """Handle new MQTT availability messages."""
            if payload == self._payload_available:
                self._available = True
            elif payload == self._payload_not_available:
                self._available = False

            self.async_schedule_update_ha_state()

        if self._state_switch_open_topic is None:
            # Force into optimistic mode.
            self._optimistic = True
        else:
            yield from mqtt.async_subscribe(
                self.hass, self._state_switch_open_topic,
                state_message_received, self._qos)
            yield from mqtt.async_subscribe(
                self.hass, self._state_switch_close_topic,
                state_message_received, self._qos)

        if self._availability_topic is not None:
            yield from mqtt.async_subscribe(
                self.hass, self._availability_topic,
                availability_message_received, self._qos)

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    def calculate_aprox_position(self, tic_last_action, action_is_opening):
        duration = (utcnow() - tic_last_action).total_seconds()
        percentage_moved = int(100 * duration / self._delay_full_open)

        if action_is_opening and percentage_moved > 99:
            self._position = 100
        elif not action_is_opening and percentage_moved > 99:
            self._position = 0
        elif self._position is not None and action_is_opening:
            self._position += percentage_moved
            if self._position > 100:
                self._position = 100
        elif self._position is not None:
            self._position -= percentage_moved
            if self._position < 0:
                self._position = 0
        else:
            self._position = percentage_moved
        _LOGGER.warning("Cover moved %d%% [%.1f s] to new position %d",
                        percentage_moved, duration, self._position)

    def calculate_stop_time(self, is_opening, **kwargs):
        position = self._position
        if position is None and is_opening:
            position = 0
        elif position is None:
            position = 100

        if ATTR_POSITION in kwargs:
            seconds = round(
                max(min(abs(kwargs[ATTR_POSITION] - position), 100), 5)
                * self._delay_full_open / 100, 1)
        elif is_opening:
            seconds = round(max(abs(100 - position), 5)
                            * self._delay_full_open / 100, 1)
        else:
            seconds = round(max(position, 5) * self._delay_full_open / 100, 1)

        self._last_action_is_opening = is_opening
        self._tic_last_action = utcnow()
        when = self._tic_last_action + timedelta(seconds=seconds)
        _LOGGER.info('STOP TIME in {:.2f} s (is_opening: {}, position now: {})'
                     .format(seconds, is_opening, position))
        return when

    @property
    def supported_features(self):
        """Flag supported features."""
        supported_features = OPEN_CLOSE_FEATURES | SUPPORT_SET_POSITION

        return supported_features

    @asyncio.coroutine
    def async_open_cover(self, **kwargs):
        """Move the cover up.

        This method is a coroutine.
        """
        _LOGGER.info("Opening cover %s", self.name)
        yield from self.async_stop_cover(is_safe_stop=True)
        when = self.calculate_stop_time(True, **kwargs)
        self._stop_checker = async_track_point_in_time(
            self.hass, self.async_stop_cover(), when)
        mqtt.async_publish(
            self.hass, self._command_switch_open_topic, self._payload_open,
            self._qos, self._retain)
        if self._optimistic:
            # Optimistically assume that cover has changed state.
            self._state_sw_open = True
            self._state_sw_close = False
            self.async_schedule_update_ha_state()

    @asyncio.coroutine
    def async_close_cover(self, **kwargs):
        """Move the cover down.

        This method is a coroutine.
        """
        _LOGGER.info("Closing cover %s", self.name)
        yield from self.async_stop_cover(is_safe_stop=True)
        when = self.calculate_stop_time(False, **kwargs)
        self._stop_checker = async_track_point_in_time(
            self.hass, self.async_stop_cover(is_timeout=True), when)
        mqtt.async_publish(
            self.hass, self._command_switch_close_topic, self._payload_close,
            self._qos, self._retain)
        if self._optimistic:
            # Optimistically assume that cover has changed state.
            self._state_sw_open = False
            self._state_sw_close = True
            self.async_schedule_update_ha_state()

    @asyncio.coroutine
    def async_stop_cover(self, **kwargs):
        """Stop the device.

        This method is a coroutine.
        """
        if 'is_safe_stop' not in kwargs:
            _LOGGER.info("Stop cover %s", self.name)
        if (self._stop_checker is not None and
                ('is_timeout' not in kwargs or not kwargs['is_timeout'])):
            self._stop_checker()
            self._stop_checker = None
        if self._tic_last_action is not None:
            self.calculate_aprox_position(
                self._tic_last_action, self._last_action_is_opening)
            self._tic_last_action = None
        mqtt.async_publish(
            self.hass, self._command_switch_close_topic,
            self._payload_stop_close, self._qos, self._retain)
        mqtt.async_publish(
            self.hass, self._command_switch_open_topic,
            self._payload_stop_open, self._qos, self._retain)
        if self._optimistic:
            # Optimistically assume that cover has changed state.
            self._state_sw_open = False
            self._state_sw_close = False
            self.async_schedule_update_ha_state()

    @asyncio.coroutine
    def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        is_opening = self._position is None or \
                        kwargs[ATTR_POSITION] > self._position
        if is_opening:
            yield from self.async_open_cover(**kwargs)
        else:
            yield from self.async_close_cover(**kwargs)
