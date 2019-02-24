"""
Support for MotionEye Cameras.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/camera.motioneye/
"""
import asyncio
import logging
from urllib.parse import urlparse
import re

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.const import CONF_NAME
from homeassistant.components.camera import (
    PLATFORM_SCHEMA, DEFAULT_CONTENT_TYPE, Camera)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.util.dt import utcnow
from homeassistant.util.async_ import run_coroutine_threadsafe

# TODO http://192.168.1.30:7999/3/config/set?emulate_motion=on/off
# TODO implement ffmpeg_output_movies control: curl http://192.168.1.30:7999/3/config/set?ffmpeg_output_movies=off

_LOGGER = logging.getLogger(__name__)

CONF_CONTROL_PORT = 'control_port'
CONF_CONTROL_CAM_ID = 'camera_id'
CONF_SNAPSHOT_URL = 'snapshot_url'
CONF_WITH_MOTION_CONTROL = 'with_motion_control'

DEFAULT_NAME = 'MotionEye Camera'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SNAPSHOT_URL): cv.url,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_WITH_MOTION_CONTROL, default=False): cv.boolean,
    vol.Optional(CONF_CONTROL_PORT, default=7999): cv.positive_int,
    vol.Optional(CONF_CONTROL_CAM_ID, default=1): cv.positive_int
})

RG_STATUS = re.compile('> Detection status (\w+)\n')
RG_CONTROL = re.compile('> Detection (\w+)\n')


# pylint: disable=unused-argument
async def async_setup_platform(hass, config,
                               async_add_entities, discovery_info=None):
    """Set up a generic IP Camera."""
    async_add_entities([MotionEyeCamera(hass, config)])


class MotionEyeCamera(Camera):
    """A very simple implementation of a MotionEye camera,
    using the snapshot url."""

    def __init__(self, hass, device_info):
        """Initialize a generic camera."""
        super().__init__()
        self.hass = hass
        self._name = device_info.get(CONF_NAME)
        self.content_type = DEFAULT_CONTENT_TYPE
        self._snapshot_url = device_info[CONF_SNAPSHOT_URL]
        self._control_url = None
        self._with_motion_detection = device_info[CONF_WITH_MOTION_CONTROL]
        if self._with_motion_detection:
            # ParseResult(scheme, netloc, url, params, query, fragment)
            url_p = urlparse(self._snapshot_url)
            control_port = device_info[CONF_CONTROL_PORT]
            cam_id = device_info[CONF_CONTROL_CAM_ID]
            self._control_url = (
                f"{url_p.scheme}://{url_p.netloc.split(':')[0]}"
                f":{control_port}/{cam_id}/detection/")
            # await self.async_get_camera_motion_status(command='status')

        self._last_image = None
        self._last_status = None
        self._motion_detection_active = False
        self.is_streaming = False
        # self._motion_detected = False

    @property
    def is_recording(self):
        """Return true if the device is recording."""
        # return self._motion_detected
        return self._motion_detection_active

    @property
    def brand(self):
        """Return the camera brand."""
        return "MotionEye"

    @property
    def motion_detection_enabled(self):
        """Return the camera motion detection status."""
        return self._motion_detection_active

    @property
    def model(self):
        """Return the camera model."""
        return "MotionEye Snapshot Camera"

    async def async_enable_motion_detection(self):
        """Enable motion detection in the camera."""
        self.is_streaming = True
        await self.async_get_camera_motion_status(command='start')
        self.async_schedule_update_ha_state()
        # self.async_schedule_update_ha_state()

    async def async_disable_motion_detection(self):
        """Disable motion detection in camera."""
        self.is_streaming = False
        await self.async_get_camera_motion_status(command='pause')
        self.async_schedule_update_ha_state()
        # self.async_schedule_update_ha_state()

    def camera_image(self):
        """Return bytes of camera image."""
        return run_coroutine_threadsafe(
            self.async_camera_image(), self.hass.loop).result()

    async def async_camera_image(self):
        """Return a still image response from the camera."""
        try:
            websession = async_get_clientsession(self.hass)
            with async_timeout.timeout(10, loop=self.hass.loop):
                response = await websession.get(self._snapshot_url)
            self._last_image = await response.read()
            if (self._control_url is None or
                    (self._last_status is not None
                     and (utcnow() - self._last_status).total_seconds() < 60)):
                return self._last_image

            await self.async_get_camera_motion_status(command='status')
            # url = self._control_url + 'status'
            # reg_expr = RG_STATUS
            # with async_timeout.timeout(5, loop=self.hass.loop):
            #     response = await websession.get(url)
            # raw = await response.read()
            # if not raw:
            #     _LOGGER.error(f"No control response in {url}")
            #     return self._last_image
            #
            # status_found = reg_expr.findall(raw.decode())
            # if not status_found:
            #     _LOGGER.error(f"Bad control response from {url}: "
            #                   f"{raw}, no pattern found")
            #     return self._last_image
            #
            # self._last_status = utcnow()
            # if status_found[0] in ['ACTIVE', 'resumed']:
            #     self._motion_detection_active = True
            # else:
            #     self._motion_detection_active = False
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout getting camera image")
            return self._last_image
        except aiohttp.ClientError as err:
            _LOGGER.error("ClientError getting new camera image for %s: %s",
                          self.name, err)
            return self._last_image

        return self._last_image

    async def async_get_camera_motion_status(self, command='status'):
        """Asks for the motion detection status of the camera."""
        if self._control_url is None:
            self._motion_detection_active = False
            return

        url = self._control_url + command
        reg_expr = RG_STATUS if command == 'status' else RG_CONTROL
        try:
            websession = async_get_clientsession(self.hass)
            with async_timeout.timeout(10, loop=self.hass.loop):
                response = await websession.get(url)
            raw = await response.read()
            if not raw:
                _LOGGER.error(f"No control response in {url}")

            status_found = reg_expr.findall(raw.decode())
            if not status_found:
                _LOGGER.error(f"Bad control response from {url}: "
                              f"{raw}, no pattern found")
            if status_found[0] in ['ACTIVE', 'resumed']:
                self._motion_detection_active = True
            else:
                self._motion_detection_active = False
            self._last_status = utcnow()
        except asyncio.TimeoutError:
            _LOGGER.warning(f"Timeout in motion detection control at {url}")
            # return
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Error in motion detection control at {url}: "
                          f"{str(err)}")
            # return

        # self.async_schedule_update_ha_state()
        # return

    @property
    def name(self):
        """Return the name of this device."""
        return self._name
