"""
Sensor for checking the standard price of the electricity (PVPC) in Spain.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.elecprice_spain_pvpc/
"""
import asyncio
import logging
from datetime import datetime, timedelta

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA, ENTITY_ID_FORMAT
from homeassistant.const import CONF_NAME, CONF_TIMEOUT
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.event import track_time_change, track_point_in_time
from homeassistant.helpers.restore_state import async_get_last_state
from homeassistant.util import Throttle
import homeassistant.util.dt as dt_util

# TODO request async
REQUIREMENTS = ['requests', 'beautifulsoup4==4.6.0']

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


def scrap_pvpc_current_prices(rate=RATES[0], timeout=10):
    """Simple scraper of the electricity prices per hour."""

    def _clean_div_price(text):
        return float(text.rstrip().lstrip().rstrip(' €/kWh').split()[-1])

    from bs4 import BeautifulSoup as Soup
    import requests

    url = 'https://tarifaluzhora.es/?tarifa=' + rate
    try:
        req = requests.get(url, timeout=timeout)
    except requests.exceptions.Timeout:
        _LOGGER.error("Timeout error requesting data from '%s'", url)
        return None
    if not req.ok:
        _LOGGER.error("Request error in '%s' [status: %d]",
                      url, req.status_code)
        return None
    # s = Soup(req.text, 'html5lib')
    s = Soup(req.text, 'html.parser')
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
        date = datetime.strptime(
            s.find_all('input', attrs={"type": "date"})[0].attrs['max'],
            '%Y-%m-%d').date()
        return date, prices
    # else:
        # TODO scrap main source in 'https://www.esios.ree.es/es/pvpc'
    _LOGGER.error("Parsing error: '%s'", str(prices))
    return None


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the electricity price sensor."""
    add_devices([ElecPriceSensor(hass,
                                 config.get(CONF_NAME),
                                 config.get(CONF_ELEC_RATE),
                                 config.get(CONF_TIMEOUT))], True)


class ElecPriceSensor(Entity):
    """Class to hold the prices of electricity as a sensor."""

    def __init__(self, hass, name, rate, timeout):
        """Initialize the sensor object."""
        self.hass = hass
        self._name = name
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, self._name, hass=self.hass)
        self.rate = rate
        self._timeout = timeout
        self._attributes = {ATTR_RATE: self.rate.upper()}
        self._state = None
        self._today_prices = None
        self._tomorrow_prices = None
        track_time_change(self.hass, self.update, second=[0], minute=[0])
        _LOGGER.debug("Setup of %s (%s) ok", self.name, self.entity_id)

    @asyncio.coroutine
    def async_added_to_hass(self):
        """Handle all entity which are about to be added."""
        state = yield from async_get_last_state(self.hass, self.entity_id)
        if not state:
            return
        self._state = state.state

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

    @Throttle(timedelta(seconds=1800))
    def update(self, *args):
        """Update the sensor."""
        # _LOGGER.warning('In update with: {}'.format(args))
        data = scrap_pvpc_current_prices(rate=self.rate, timeout=self._timeout)
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
                _LOGGER.debug("Updating today prices: %s", str(prices))
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
        else:
            self._state = None
            _LOGGER.warning("Trying to update later, after %d seconds",
                            self._timeout)
            track_point_in_time(
                self.hass, self.update,
                dt_util.now() + timedelta(seconds=self._timeout))

        self.schedule_update_ha_state(False)


if __name__ == '__main__':
    scrap_pvpc_current_prices()
