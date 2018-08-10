"""
Sensor for checking the standard price of the electricity (PVPC) in Spain.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.elecprice_spain_pvpc/
"""
import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp
import async_timeout
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.sensor import PLATFORM_SCHEMA, ENTITY_ID_FORMAT
from homeassistant.const import CONF_NAME, CONF_TIMEOUT
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.event import (
    async_track_point_in_time, async_track_time_change)
import homeassistant.util.dt as dt_util


REQUIREMENTS = ['beautifulsoup4']

_LOGGER = logging.getLogger(__name__)

ATTR_PRICE = "Precio"
ATTR_RATE = "Tarifa"
ATTR_TOMORROW_PRICES = "Precios para mañana"
CONF_ELEC_RATE = 'electric_rate'
DEFAULT_NAME = 'PVPC'
ICON = "mdi:currency-eur"
RATES = ['normal', 'discriminacion', 'coche_electrico']
SENSOR_DEVICEID = 'sensor.pvpc'
UNIT = "€/kWh"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_ELEC_RATE, default=RATES[0]): vol.In(RATES),
    vol.Optional(CONF_TIMEOUT, default=10): cv.positive_int,
})


def scrap_pvpc_current_prices(html_text):
    """Simple scraper of the electricity prices per hour."""

    def _clean_div_price(text):
        return float(text.rstrip().lstrip().rstrip(' €/kWh').split()[-1])

    from bs4 import BeautifulSoup as Soup

    # s = Soup(html_text, 'html5lib')
    s = Soup(html_text, 'html.parser')
    hour_prices = s.find_all('div', id='hour_prices')
    if not hour_prices:
        _LOGGER.error("Prices not found in HTML data")
        return None

    try:
        prices = [_clean_div_price(div.text) for div in s.find_all(
                'div', id='hour_prices')[0].find_all(
            'div', attrs={'class': 'col-xs-9'})]
    except Exception as exc:
        _LOGGER.error("Parsing exception: %s [%s]", str(exc), exc.__class__)
        return None
    if prices and len(prices) == 24:
        try:
            date = datetime.strptime(
                s.find_all('input', attrs={"name": "date"})[0].attrs['max'],
                '%Y-%m-%d').date()
            return date, prices
        except IndexError:
            return dt_util.utcnow().date(), prices
    # else:
        # TODO scrap main source in 'https://www.esios.ree.es/es/pvpc'
    _LOGGER.error("Parsing error: '%s'", str(prices))
    return None


async def async_setup_platform(hass, config, async_add_devices,
                               discovery_info=None):
    """Set up the electricity price sensor."""
    websession = async_get_clientsession(hass)
    async_add_devices(
        [ElecPriceSensor(hass, websession,
                         config.get(CONF_NAME),
                         config.get(CONF_ELEC_RATE),
                         config.get(CONF_TIMEOUT))])


class ElecPriceSensor(Entity):
    """Class to hold the prices of electricity as a sensor."""

    def __init__(self, hass, websession, name, rate, timeout):
        """Initialize the sensor object."""
        self.hass = hass
        self._websession = websession
        self._name = name
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, self._name, hass=self.hass)
        self.rate = rate
        self._timeout = timeout
        self._attributes = {ATTR_RATE: self.rate.upper()}
        self._state = None
        self._today_prices = None
        self._tomorrow_prices = None
        async_track_time_change(self.hass, self.async_update,
                                second=[0], minute=[0, 15, 30, 45])
        _LOGGER.info("Setup of %s (%s) ok", self.name, self.entity_id)

    async def async_added_to_hass(self):
        """Handle all entity which are about to be added."""
        await self.async_update()

    @property
    def should_poll(self):
        """Return True if entity has to be polled for state.

        False if entity pushes its state to HA.
        """
        return False

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the price of electricity."""
        return UNIT

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return ICON

    @property
    def device_state_attributes(self):
        """Attributes."""
        return self._attributes

    async def async_update(self, *args):
        """Update the sensor."""
        url = 'https://tarifaluzhora.es/?tarifa=' + self.rate
        data = None
        try:
            with async_timeout.timeout(self._timeout, loop=self.hass.loop):
                req = await self._websession.get(url)
                if req.status < 400:
                    text = await req.text()
                    data = scrap_pvpc_current_prices(text)
                else:
                    _LOGGER.error("Request error in '%s' [status: %d]",
                                  url, req.status)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout error requesting data from '%s'", url)
        except aiohttp.ClientError:
            _LOGGER.error("Client error in '%s'", url)

        if data:
            date, prices = data
            if args:
                now = args[0]
            else:
                now = dt_util.now()
            today = now.date()
            if today < date:
                _LOGGER.warning("Setting tomorrow (%s) prices: %s",
                                date.strftime('%Y-%m-%d'), str(prices))
                self._tomorrow_prices = prices
            elif today == date:
                _LOGGER.warning("Updating today prices: %s", str(prices))
                self._today_prices = prices
            else:
                _LOGGER.error("Bad date scrapping data? '%s', prices: %s",
                              date.strftime('%Y-%m-%d'), str(prices))
                self._tomorrow_prices = None

            if self._today_prices is not None:
                self._state = self._today_prices[now.hour]
                # self._attributes[ATTR_TODAY_PRICES] = self._today_prices
                for i, p in enumerate(self._today_prices):
                    key = ATTR_PRICE + ' {:02d}h'.format(i)
                    self._attributes[key] = p
                _LOGGER.info("Price at %dh: %.5f €/kWh", now.hour, self._state)

            if self._tomorrow_prices is not None:
                self._attributes[ATTR_TOMORROW_PRICES] = self._tomorrow_prices
            elif ATTR_TOMORROW_PRICES in self._attributes:
                self._attributes.pop(ATTR_TOMORROW_PRICES)
        elif self._today_prices is not None:
            now = dt_util.now()
            self._state = self._today_prices[now.hour]
        else:
            self._state = None
            _LOGGER.warning("Trying to update later, after %d seconds",
                            self._timeout)
            async_track_point_in_time(
                self.hass, self.async_update,
                dt_util.now() + timedelta(seconds=3 * self._timeout))

        self.async_schedule_update_ha_state()


# if __name__ == '__main__':
#     import requests
#
#     url = 'https://tarifaluzhora.es/?tarifa=' + RATES[1]
#     req_data = None
#     try:
#         req = requests.get(url, timeout=10)
#         if not req.ok:
#             print("Request error in '%s' [status: %d]", url, req.status_code)
#         else:
#             req_data = req.text
#     except requests.exceptions.Timeout:
#         print("Timeout error requesting data from '%s'", url)
#
#     if req_data:
#         prices = scrap_pvpc_current_prices(req_data)
#         print(prices)
