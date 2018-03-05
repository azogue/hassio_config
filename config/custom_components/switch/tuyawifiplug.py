"""
Support for Tuya Wifi smart switches.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/switch.tuyawifiplug/
"""
import base64
from hashlib import md5
import json
import logging
import socket
import time

import voluptuous as vol

from homeassistant.components.switch import (
    SwitchDevice, PLATFORM_SCHEMA, ENTITY_ID_FORMAT)
from homeassistant.const import (CONF_HOST, CONF_NAME, CONF_SWITCHES)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import async_generate_entity_id
import datetime as dt


# Python module to interface with Shenzhen Xenon ESP8266MOD WiFi smart devices
# E.g. https://wikidevi.com/wiki/Xenon_SM-PW701U
#   SKYROKU SM-PW701U Wi-Fi Plug Smart Plug
#   Wuudi SM-S0301-US - WIFI Smart Power Socket Multi Plug with 4 AC Outlets and 4 USB Charging Works with Alexa
#
# This would not exist without the protocol reverse engineering from
# https://github.com/codetheweb/tuyapi by codetheweb and blackrozes
#
# Tested with Python 3.6



REQUIREMENTS = ['pycryptodome==3.4.11']
_LOGGER = logging.getLogger(__name__)

CONF_DEVICE_ID = 'device_id'
CONF_LOCAL_KEY = 'local_key'
DEFAULT_NAME = 'Tuya Wifi Switch'
PROTOCOL_VERSION_BYTES = b'3.1'
SET = 'set'

SWITCH_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_DEVICE_ID): cv.string,
    vol.Required(CONF_LOCAL_KEY): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
}, extra=vol.ALLOW_EXTRA)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SWITCHES): vol.Schema({cv.slug: SWITCH_SCHEMA}),
})

# ------------------------------------------------------------------------


class AESCipher(object):
    def __init__(self, key):
        self.bs = 16
        self.key = key
        self._Crypto = self._AES = self._pyaes = None
        import Crypto
        from Crypto.Cipher import AES  # PyCrypto
        _LOGGER.debug("Using Crypto ({})".format(Crypto.__file__))
        self._Crypto = Crypto
        self._AES = AES

    def encrypt(self, raw):
        raw = self._pad(raw)
        cipher = self._AES.new(self.key, mode=self._AES.MODE_ECB)
        crypted_text = cipher.encrypt(raw)
        return base64.b64encode(crypted_text)

    def decrypt(self, enc):
        enc = base64.b64decode(enc)
        cipher = self._AES.new(self.key, self._AES.MODE_ECB)
        raw = cipher.decrypt(enc)
        return self._unpad(raw).decode('utf-8')

    def _pad(self, s):
        padnum = self.bs - len(s) % self.bs
        return s + padnum * chr(padnum).encode()

    @staticmethod
    def _unpad(s):
        return s[:-ord(s[len(s) - 1:])]


def bin2hex(x, pretty=False):
    if pretty:
        space = ' '
    else:
        space = ''
    return ''.join('%02X%s' % (y, space) for y in x)


def hex2bin(x):
    return bytes.fromhex(x)


class XenonDevice(object):
    def __init__(self, dev_id, address, local_key=None, dev_type=None,
                 connection_timeout=5):
        """
        Represents a Tuya device.

        Args:
            dev_id (str): The device id.
            address (str): The network address.
            local_key (str, optional): The encryption key. Defaults to None.
            dev_type (str, optional): The device type.
                It will be used as key for lookups in payload_dict.
                Defaults to None.

        Attributes:
            port (int): The port to connect to.
        """
        # This is intended to match requests.json payload at https://github.com/codetheweb/tuyapi
        self._payload_dict = {
            "outlet": {
                "status": {
                    "hexByte": "0a",
                    "command": {"gwId": "", "devId": ""}
                },
                "set": {
                    "hexByte": "07",
                    "command": {"devId": "", "uid": "", "t": ""}
                },
                "prefix": "000055aa00000000000000",
            # Next byte is command byte ("hexByte") some zero padding, then length of remaining payload, i.e. command + suffix (unclear if multiple bytes used for length, zero padding implies could be more than one byte)
                "suffix": "000000000000aa55"
            }
        }
        self.id = dev_id
        self.address = address
        self.local_key = local_key.encode('latin1')
        self.dev_type = dev_type
        self.connection_timeout = connection_timeout
        self.port = 6668  # default - do not expect caller to pass in

    def __repr__(self):
        return '%r' % (
        (self.id, self.address),)  # FIXME can do better than this

    def _send_receive(self, payload):
        """
        Send single buffer `payload` and receive a single buffer.

        Args:
            payload(bytes): Data to send.
        """
        retries = 0
        data = None
        while retries < 3:
            retries += 1
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(self.connection_timeout)
                    s.connect((self.address, self.port))
                    s.send(payload)
                    data = s.recv(1024)
                    s.shutdown(socket.SHUT_RDWR)
                break
            except (OSError, ConnectionResetError, socket.timeout) as exc:
                if retries > 2:
                    _LOGGER.warning("Connection Error: %s [%s]",
                                    str(exc), exc.__class__)
            except Exception as exc:
                _LOGGER.error("Could not socket connect: %s [%s]",
                              str(exc), exc.__class__)
                return data

        if data is None:
            _LOGGER.warning("There were socket ConnectionResetErrors [{}] [{}]".format(retries, dt.datetime.now()))
        else:
            _LOGGER.info("OK [{}]: {} -> {}".format(retries, dt.datetime.now(), data[20:-8]))
        return data

    def generate_payload(self, command, data=None):
        """
        Generate the payload to send.

        Args:
            command(str): The type of command.
                This is one of the entries from payload_dict
            data(dict, optional): The data to be send.
                This is what will be passed via the 'dps' entry
        """
        json_data = self._payload_dict[self.dev_type][command]['command']

        if 'gwId' in json_data:
            json_data['gwId'] = self.id
        if 'devId' in json_data:
            json_data['devId'] = self.id
        if 'uid' in json_data:
            json_data['uid'] = self.id  # still use id, no seperate uid
        if 't' in json_data:
            json_data['t'] = str(int(time.time()))

        if data is not None:
            json_data['dps'] = data

        # Create byte buffer from hex data
        json_payload = json.dumps(json_data)
        # print(json_payload)
        json_payload = json_payload.replace(' ',
                                            '')  # if spaces are not removed device does not respond!
        json_payload = json_payload.encode('utf-8')
        _LOGGER.debug('json_payload=%r', json_payload)

        if command == SET:
            # need to encrypt
            # print('json_payload %r' % json_payload)
            self.cipher = AESCipher(
                self.local_key)  # expect to connect and then disconnect to set new
            json_payload = self.cipher.encrypt(json_payload)
            # print('crypted json_payload %r' % json_payload)
            preMd5String = b'data=' + json_payload + b'||lpv=' + PROTOCOL_VERSION_BYTES + b'||' + self.local_key
            # print('preMd5String %r' % preMd5String)
            m = md5()
            m.update(preMd5String)
            # print(repr(m.digest()))
            hexdigest = m.hexdigest()
            # print(hexdigest)
            # print(hexdigest[8:][:16])
            json_payload = PROTOCOL_VERSION_BYTES + hexdigest[8:][:16].encode(
                'latin1') + json_payload
            # print('data_to_send')
            # print(json_payload)
            # print('crypted json_payload (%d) %r' % (len(json_payload), json_payload))
            # print('json_payload  %r' % repr(json_payload))
            # print('json_payload len %r' % len(json_payload))
            # print(bin2hex(json_payload))
            self.cipher = None  # expect to connect and then disconnect to set new

        postfix_payload = hex2bin(
            bin2hex(json_payload) +
            self._payload_dict[self.dev_type]['suffix'])
        # print('postfix_payload %r' % postfix_payload)
        # print('postfix_payload %r' % len(postfix_payload))
        # print('postfix_payload %x' % len(postfix_payload))
        # print('postfix_payload %r' % hex(len(postfix_payload)))
        assert len(postfix_payload) <= 0xff
        postfix_payload_hex_len = '%x' % len(
            postfix_payload)  # TODO this assumes a single byte 0-255 (0x00-0xff)
        buffer = hex2bin(
            self._payload_dict[self.dev_type]['prefix'] +
            self._payload_dict[self.dev_type][command]['hexByte'] +
            '000000' +
            postfix_payload_hex_len) + postfix_payload
        # print('command', command)
        # print('prefix')
        # print(self._payload_dict[self.dev_type][command]['prefix'])
        # print(repr(buffer))
        # print(bin2hex(buffer, pretty=True))
        # print(bin2hex(buffer, pretty=False))
        # print('full buffer(%d) %r' % (len(buffer), buffer))
        return buffer


class OutletDevice(XenonDevice):
    def __init__(self, dev_id, address, local_key=None, dev_type=None):
        dev_type = dev_type or 'outlet'
        super(OutletDevice, self).__init__(dev_id, address, local_key,
                                           dev_type)

    def status(self):
        _LOGGER.debug('status() entry')
        # open device, send request, then close connection
        payload = self.generate_payload('status')

        data = self._send_receive(payload)
        if data is None:
            return None

        _LOGGER.debug('status received data=%r', data)

        result = data[20:-8]  # hard coded offsets
        _LOGGER.debug('result=%r', result)
        # result = data[data.find('{'):data.rfind('}')+1]  # naive marker search, hope neither { nor } occur in header/footer
        # print('result %r' % result)
        if result.startswith(b'{'):
            # this is the regular expected code path
            result = json.loads(result.decode())
        elif result.startswith(PROTOCOL_VERSION_BYTES):
            # got an encrypted payload, happens occasionally
            # expect resulting json to look similar to:: {"devId":"ID","dps":{"1":true,"2":0},"t":EPOCH_SECS,"s":3_DIGIT_NUM}
            # NOTE dps.2 may or may not be present
            # remove version header
            result = result[len(PROTOCOL_VERSION_BYTES):]
            # remove (what I'm guessing, but not confirmed is) 16-bytes of MD5 hexdigest of payload
            result = result[16:]
            cipher = AESCipher(self.local_key)
            result = cipher.decrypt(result)
            _LOGGER.debug('decrypted result=%r', result)
            try:
                result = json.loads(result.decode())
            except AttributeError:
                result = json.loads(result)
        else:
            _LOGGER.error('Unexpected status() payload=%r', result)

        return result

    def set_status(self, on, switch=1):
        """
        Set status of the device to 'on' or 'off'.

        Args:
            on(bool):  True for 'on', False for 'off'.
            switch(int): The switch to set
        """
        # open device, send request, then close connection
        if isinstance(switch, int):
            switch = str(switch)  # index and payload is a string
        payload = self.generate_payload(SET, {switch: on})
        # print('payload %r' % payload)

        data = self._send_receive(payload)
        _LOGGER.debug('set_status received data=%r', data)

        return data

    def set_timer(self, num_secs):
        """
        Set a timer.

        Args:
            num_secs(int): Number of seconds
        """
        # FIXME / TODO support schemas? Accept timer id number as parameter?

        # Dumb heuristic; Query status, pick last device id as that is probably the timer
        status = self.status()
        if not status:
            return None

        devices = status['dps']
        devices_numbers = list(devices.keys())
        devices_numbers.sort()
        dps_id = devices_numbers[-1]

        payload = self.generate_payload(SET, {dps_id: num_secs})

        data = self._send_receive(payload)
        _LOGGER.info('set_timer received data=%r', data)
        return data

# ------------------------------------------------------------------------


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the TPLink switch platform."""
    switches = []
    for device, device_config in config[CONF_SWITCHES].items():
        switches.append(TuyaSwitch(
            hass, device,
            device_config.get(CONF_NAME),
            device_config.get(CONF_HOST),
            device_config.get(CONF_DEVICE_ID),
            device_config.get(CONF_LOCAL_KEY)))

    add_devices(switches, True)


class TuyaSwitch(SwitchDevice):
    """Representation of a Tuya wifi smart switch."""

    def __init__(self, hass, device_id, friendly_name, host, uuid, local_key):
        """Initialize the switch."""
        # from pytuya import OutletDevice
        self.hass = hass
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, device_id, hass=hass)
        # OutletDevice('DEVICE_ID_HERE', 'IP_ADDRESS_HERE', 'LOCAL_KEY_HERE')
        self._smartplug = OutletDevice(uuid, host, local_key)
        self._name = friendly_name
        self._state = None
        self._available = True

    @property
    def name(self):
        """Return the name of the Smart Plug, if any."""
        return self._name

    @property
    def available(self):
        """Return if switch is available."""
        return self._available

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._state

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        self._smartplug.set_status(True, switch=1)
        self._state = True

    def turn_off(self):
        """Turn the switch off."""
        self._smartplug.set_status(False, switch=1)
        self._state = False

    def update(self):
        """Update the Smart Plug state."""

        # from pyHS100 import SmartDeviceException
        try:
            data = self._smartplug.status()
            if not data:
                self._available = False
                return
            self._state = data['dps']['1']
            self._available = True
        except ConnectionResetError as exc:
            _LOGGER.warning("Could not read state for %s: ConnectionReset: %s",
                            self.name, str(exc))
            self._available = False
            return
        except Exception as exc:
            _LOGGER.error("Could not read state for %s: %s [%s]",
                          self.name, str(exc), exc.__class__)
            self._available = False
            return
