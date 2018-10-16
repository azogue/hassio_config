"""
Sensor for checking the standard price of the electricity (PVPC) in Spain.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.elecprice_spain_pvpc/
"""
import asyncio
import logging
from datetime import datetime, timedelta
import pytz

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


def scrap_xml_official_pvpc_current_prices(html_text, periodo=1):
    from bs4 import BeautifulSoup as Soup
    ident_tarifa = 'Z0{}'.format(periodo)
    ident_precio = 'FEU'

    soup_pvpc = Soup(html_text, "html5lib")
    tz = pytz.timezone('Europe/Madrid')
    str_horiz = soup_pvpc.find_all('horizonte')[0]['v']
    ts_st, _ = [parse(t).astimezone(tz).date() for t in str_horiz.split('/')]

    for serie in soup_pvpc.find_all('identificacionseriestemporales'):
        columna = serie.find_next('terminocostehorario')['v']
        if columna == ident_precio \
                and len(serie.find_all('tipoprecio')) > 0 \
                and serie.tipoprecio['v'] == ident_tarifa:
            values = [float(v['v']) for v in serie.find_all('ctd')]
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
        date = datetime.today().strftime('%Y-%m-%d')
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

        if text:
            date, prices = scrap_xml_official_pvpc_current_prices(text, period)
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
                _LOGGER.info("Updating today prices: %s", str(prices))
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

        await self.async_update_ha_state()


if __name__ == '__main__':
    example_raw = '''<PVPCDesgloseHorario xmlns="http://sujetos.esios.ree.es/schemas/2014/04/01/PVPCDesgloseHorario-esios-MP/">
<IdentificacionMensaje v="pvpcdesglosehorario_20180831"/>
<VersionMensaje v="1"/>
<TipoMensaje v="Z55"/>
<TipoProceso v="A01"/>
<TipoClasificacion v="A01"/>
<IdentificacionRemitente codificacion="A01" v="10XES-REE------E"/>
<FuncionRemitente v="A04"/>
<IdentificacionDestinatario codificacion="A01" v="10XES-REE------E"/>
<FuncionDestinatario v="A04"/>
<FechaHoraMensaje v="2018-08-30T18:50:38Z"/>                        
<Horizonte v="2018-08-30T22:00Z/2018-08-31T22:00Z"/>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST1"/><TerminoCosteHorario v="CAPh"/><TipoPrecio v="Z01"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00463"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00463"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST2"/><TerminoCosteHorario v="CAPh"/><TipoPrecio v="Z02"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.000805"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.000805"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST3"/><TerminoCosteHorario v="CAPh"/><TipoPrecio v="Z03"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.001087"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.000644"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.000644"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.000644"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.000644"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.000644"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.000644"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.001087"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.001087"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.001087"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.001087"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.001087"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.001087"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.004771"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.001087"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST4"/><TerminoCosteHorario v="CCOMh"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00003357"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00003357"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST5"/><TerminoCosteHorario v="CCOSh"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00012772"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00012772"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST6"/><TerminoCosteHorario v="CCVh"/><TipoPrecio v="Z01"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.001933"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00188"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00185"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.001828"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.001829"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.001825"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.001916"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.002053"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.002083"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.002093"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.002076"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.002072"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.002057"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.002044"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.002046"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00203"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.002019"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.002015"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.002047"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.002055"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.002072"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.002057"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.002016"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.001951"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST7"/><TerminoCosteHorario v="CCVh"/><TipoPrecio v="Z02"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.001875"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.001822"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.001791"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.001769"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.001771"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.001767"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.001858"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.001994"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.002025"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.002035"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.002018"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.002014"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.001998"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.002046"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.002048"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.002032"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.002021"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.002017"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.002049"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.002057"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.002074"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.002059"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.002018"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.001893"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST8"/><TerminoCosteHorario v="CCVh"/><TipoPrecio v="Z03"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.001879"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.001819"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.001789"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.001767"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.001769"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.001765"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.001856"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.001999"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.002029"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.002039"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.002022"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.002018"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.002003"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.002046"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.002048"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.002032"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.002021"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.002017"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.002049"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.002057"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.002074"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.002059"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.002018"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.001897"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST9"/><TerminoCosteHorario v="CDSVh"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00027"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00027"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST10"/><TerminoCosteHorario v="FEU"/><TipoPrecio v="Z01"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.13277651368"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.12858901768"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.12610034639"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.12422420581"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.12420919423"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.12363851107"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.12999002388"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.13981564498"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.14041216489"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.14066576915"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.13920725957"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.13880176428"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.13806632573"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.13744670589"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.13807789163"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.13752573995"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.13654351466"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.1359537335"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.13847609179"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.13949675124"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.14140881627"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.14055924443"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.13803556575"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.1340651251"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST11"/><TerminoCosteHorario v="FEU"/><TipoPrecio v="Z02"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.08308969834"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.07913085863"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.07673627434"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.07493369176"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.07498671247"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.0745061506"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.08077911199"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.09050552596"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.09151014932"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.09184620287"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.09051196758"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.09011915929"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.08931584045"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.15625101521"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.15696617524"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.15640575356"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.15541635627"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.15474381782"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.15728329511"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.15839162285"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.16031501188"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.15953973833"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.15699009365"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.08440228705"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST12"/><TerminoCosteHorario v="FEU"/><TipoPrecio v="Z03"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.08769517613"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.07567381622"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.07333941193"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.07164295564"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.07169328335"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.07128357277"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.07746392545"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.09480328014"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.09548349705"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.09576136331"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.09430549973"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.09382233915"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.09314498189"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.15625101521"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.15696617524"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.15640575356"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.15541635627"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.15474381782"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.15728329511"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.15839162285"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.16031501188"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.15953973833"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.15699009365"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.08899702155"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST13"/><TerminoCosteHorario v="INTh"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00104"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00104"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST14"/><TerminoCosteHorario v="OCh"/><TipoPrecio v="Z01"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00776429"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00771129"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00768129"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00765929"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00766029"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00765629"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00774729"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00788429"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00791429"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00792429"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00790729"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00790329"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00788829"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00787529"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00787729"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00786129"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00785029"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00784629"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00787829"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00788629"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00790329"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00788829"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00784729"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00778229"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST15"/><TerminoCosteHorario v="OCh"/><TipoPrecio v="Z02"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00388129"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00382829"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00379729"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00377529"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00377729"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00377329"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00386429"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00400029"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00403129"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00404129"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00402429"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00402029"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00400429"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00801829"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00802029"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00800429"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00799329"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00798929"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00802129"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00802929"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00804629"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00803129"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00799029"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00389929"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST16"/><TerminoCosteHorario v="OCh"/><TipoPrecio v="Z03"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00416729"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00366429"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00363429"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00361229"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00361429"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00361029"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00370129"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00428729"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00431729"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00432729"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00431029"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00430629"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00429129"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00801829"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00802029"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00800429"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00799329"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00798929"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00802129"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00802929"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00804629"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00803129"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00799029"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00418529"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST17"/><TerminoCosteHorario v="PMASh"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00162"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00196"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00157"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00164"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.0018"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00165"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00179"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00229"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.0029"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00262"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.0023"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00217"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00215"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00146"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00149"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00171"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00176"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.0018"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00197"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00247"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00245"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00229"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00199"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00236"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST18"/><TerminoCosteHorario v="Pmh"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.0648"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.061"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.05939"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.05788"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.05782"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.05772"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.06354"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.07199"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.07339"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.07433"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.07353"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.07338"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.0724"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.07227"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.07236"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.07111"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.07029"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.07002"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.07194"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.07196"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.07311"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.07227"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.0699"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.06525"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST19"/><TerminoCosteHorario v="SAh"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.00189"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.00223"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.00184"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.00191"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.00207"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.00192"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.00206"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.00256"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.00317"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.00289"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.00257"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.00244"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.00242"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.00173"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.00176"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.00198"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.00203"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.00207"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.00224"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.00274"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.00272"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.00256"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.00226"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.00263"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST20"/><TerminoCosteHorario v="TCUh"/><TipoPrecio v="Z01"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.08874951368"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.08456201768"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.08207334639"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.08019720581"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.08018219423"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.07961151107"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.08596302388"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.09578864498"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.09638516489"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.09663876915"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.09518025957"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.09477476428"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.09403932573"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.09341970589"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.09405089163"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.09349873995"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.09251651466"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.0919267335"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.09444909179"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.09546975124"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.09738181627"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.09653224443"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.09400856575"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.0900381251"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST21"/><TerminoCosteHorario v="TCUh"/><TipoPrecio v="Z02"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.08087469834"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.07691585863"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.07452127434"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.07271869176"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.07277171247"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.0722911506"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.07856411199"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.08829052596"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.08929514932"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.08963120287"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.08829696758"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.08790415929"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.08710084045"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.09423901521"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.09495417524"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.09439375356"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.09340435627"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.09273181782"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.09527129511"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.09637962285"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.09830301188"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.09752773833"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.09497809365"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.08218728705"/></Intervalo></Periodo></SeriesTemporales>
<SeriesTemporales><IdentificacionSeriesTemporales v="IST22"/><TerminoCosteHorario v="TCUh"/><TipoPrecio v="Z03"/><UnidadPrecio v="EUR:KWH"/><Periodo><IntervaloTiempo v="2018-08-30T22:00Z/2018-08-31T22:00Z"/><Resolucion v="PT60M"/><Intervalo><Pos v="1"/><Ctd v="0.08481617613"/></Intervalo><Intervalo><Pos v="2"/><Ctd v="0.07478781622"/></Intervalo><Intervalo><Pos v="3"/><Ctd v="0.07245341193"/></Intervalo><Intervalo><Pos v="4"/><Ctd v="0.07075695564"/></Intervalo><Intervalo><Pos v="5"/><Ctd v="0.07080728335"/></Intervalo><Intervalo><Pos v="6"/><Ctd v="0.07039757277"/></Intervalo><Intervalo><Pos v="7"/><Ctd v="0.07657792545"/></Intervalo><Intervalo><Pos v="8"/><Ctd v="0.09192428014"/></Intervalo><Intervalo><Pos v="9"/><Ctd v="0.09260449705"/></Intervalo><Intervalo><Pos v="10"/><Ctd v="0.09288236331"/></Intervalo><Intervalo><Pos v="11"/><Ctd v="0.09142649973"/></Intervalo><Intervalo><Pos v="12"/><Ctd v="0.09094333915"/></Intervalo><Intervalo><Pos v="13"/><Ctd v="0.09026598189"/></Intervalo><Intervalo><Pos v="14"/><Ctd v="0.09423901521"/></Intervalo><Intervalo><Pos v="15"/><Ctd v="0.09495417524"/></Intervalo><Intervalo><Pos v="16"/><Ctd v="0.09439375356"/></Intervalo><Intervalo><Pos v="17"/><Ctd v="0.09340435627"/></Intervalo><Intervalo><Pos v="18"/><Ctd v="0.09273181782"/></Intervalo><Intervalo><Pos v="19"/><Ctd v="0.09527129511"/></Intervalo><Intervalo><Pos v="20"/><Ctd v="0.09637962285"/></Intervalo><Intervalo><Pos v="21"/><Ctd v="0.09830301188"/></Intervalo><Intervalo><Pos v="22"/><Ctd v="0.09752773833"/></Intervalo><Intervalo><Pos v="23"/><Ctd v="0.09497809365"/></Intervalo><Intervalo><Pos v="24"/><Ctd v="0.08611802155"/></Intervalo></Periodo></SeriesTemporales>
</PVPCDesgloseHorario>
'''
    output = scrap_xml_official_pvpc_current_prices(example_raw, periodo=2)
    print(output)
