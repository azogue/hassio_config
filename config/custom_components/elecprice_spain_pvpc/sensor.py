"""
Sensor for checking the standard price of the electricity (PVPC) in Spain.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.elecprice_spain_pvpc/

# TODO Add daily fixed cost (€/day), w|wo taxes (IVA) to show fixed vs variable
* Add config parameter 'contracted_power' (kW), default: 3.3
* Add attribute 'Coste fijo, €/día':= f(contracted_power, ...)
* Add attribute 'Coste fijo con IVA, €/día':= 'Coste fijo, €/día' * 1.21
* Add attribute 'Precio con IVA, €/kWh':= state * 1.21

"""
import asyncio
import logging
from datetime import timedelta

import aiohttp
import async_timeout
from dateutil.parser import parse
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.sensor import PLATFORM_SCHEMA, ENTITY_ID_FORMAT
from homeassistant.const import CONF_NAME, CONF_TIMEOUT
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.event import (
    async_track_point_in_time, async_track_time_change)
import homeassistant.util.dt as dt_util


REQUIREMENTS = ['beautifulsoup4', 'html5lib>=1.0.1']

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


def scrap_xml_official_pvpc_current_prices(html_text, tz, periodo=1):
    from bs4 import BeautifulSoup as Soup
    ident_tarifa = 'Z0{}'.format(periodo)
    ident_precio = 'FEU'

    soup_pvpc = Soup(html_text, "html5lib")
    str_horiz = soup_pvpc.find_all('horizonte')[0]['v']
    ts_st, _ = [parse(t).astimezone(tz).date() for t in str_horiz.split('/')]

    for serie in soup_pvpc.find_all('identificacionseriestemporales'):
        columna = serie.find_next('terminocostehorario')['v']
        if columna == ident_precio \
                and len(serie.find_all('tipoprecio')) > 0 \
                and serie.tipoprecio['v'] == ident_tarifa:
            values = [round(float(v['v']), 5) for v in serie.find_all('ctd')]
            return ts_st, values
    return ts_st, []


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
        tz = self.hass.config.time_zone
        date = dt_util.now(tz).strftime('%Y-%m-%d')
        url = 'https://api.esios.ree.es/' \
              'archives/80/download?date={}'.format(date)
        period = RATES.index(self.rate) + 1
        text = None
        try:
            with async_timeout.timeout(self._timeout, loop=self.hass.loop):
                req = await self._websession.get(url)
                if req.status < 400:
                    text = await req.text()
                else:
                    _LOGGER.error("Request error in '%s' [status: %d]",
                                  url, req.status)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout error requesting data from '%s'", url)
        except aiohttp.ClientError:
            _LOGGER.error("Client error in '%s'", url)

        def _get_current_value(hourly_values, current_hour):
            """Quickfix to handle DST changes

            In DST changes, there are 23 or 25 hours, so,
            adapt index acordingly."""
            if len(hourly_values) == 23 and current_hour > 2:
                return hourly_values[current_hour - 1]
            elif len(hourly_values) == 25 and current_hour > 2:
                return hourly_values[current_hour + 1]
            # _LOGGER.warning(f"DEBUG current value: {len(hourly_values)};"
            #                f" {current_hour}, {hourly_values[current_hour]}")
            return hourly_values[current_hour]

        if text:
            date, prices = scrap_xml_official_pvpc_current_prices(
                text, tz, period)
            if args:
                now = args[0].astimezone(tz)
            else:
                now = dt_util.now(tz)
            today = now.date()
            # _LOGGER.warning(f"Using now: {now}, date: {today}")
            if today < date:
                _LOGGER.warning("Setting tomorrow (%s) prices: %s",
                                date.strftime('%Y-%m-%d'), str(prices))
                self._tomorrow_prices = prices
            elif today == date:
                _LOGGER.info("Updating today prices: %s", str(prices))
                self._today_prices = prices
            else:
                _LOGGER.error("Bad date scrapping data? '%s', prices: %s",
                              date.strftime('%Y-%m-%d'), str(prices))
                self._tomorrow_prices = None

            if self._today_prices is not None:
                self._state = _get_current_value(self._today_prices, now.hour)
                self._attributes = {}  # reset attrs
                for i, p in enumerate(self._today_prices):
                    key = ATTR_PRICE + ' {:02d}h'.format(i)
                    self._attributes[key] = p
                _LOGGER.info("Price at %dh: %.5f €/kWh", now.hour, self._state)

            if self._tomorrow_prices is not None:
                self._attributes[ATTR_TOMORROW_PRICES] = self._tomorrow_prices
            elif ATTR_TOMORROW_PRICES in self._attributes:
                self._attributes.pop(ATTR_TOMORROW_PRICES)
        elif self._today_prices is not None:
            now = dt_util.now(tz)
            self._state = _get_current_value(self._today_prices, now.hour)
        else:
            self._state = None
            _LOGGER.warning("Trying to update later, after %d seconds",
                            self._timeout)
            async_track_point_in_time(
                self.hass, self.async_update,
                dt_util.now() + timedelta(seconds=3 * self._timeout))

        await self.async_update_ha_state()
