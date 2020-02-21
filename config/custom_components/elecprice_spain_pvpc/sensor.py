"""
Sensor to collect the standard daily prices of electricity ('PVPC') in Spain.

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
from datetime import date, timedelta
from random import randint
from typing import List, Optional, Tuple

import aiohttp
import async_timeout
import voluptuous as vol
import xmltodict
from dateutil.parser import parse
from pytz import timezone

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA, ENTITY_ID_FORMAT
from homeassistant.const import ATTR_ATTRIBUTION, CONF_NAME, CONF_TIMEOUT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_change,
)
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.dt as dt_util


_LOGGER = logging.getLogger(__name__)
_RESOURCE = "https://api.esios.ree.es/archives/80/download?date={day:%Y-%m-%d}"

ATTR_PRICE = "price"
ATTR_RATE = "tariff"

ATTRIBUTION = "Data retrieved from api.esios.ree.es by REE"

DEFAULT_NAME = "PVPC"
ICON = "mdi:currency-eur"
RATES = ["normal", "discriminacion", "coche_electrico"]
UNIT = "€/kWh"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(ATTR_RATE, default=RATES[1]): vol.In(RATES),
        vol.Optional(CONF_TIMEOUT, default=10): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


def extract_prices_for_tariff(
    xml_data: str, tz: timezone, tariff: int = 2
) -> Tuple[date, List[float]]:
    """
    PVPC xml data extractor.

    Extract hourly prices for the selected tariff from the xml daily file download
    of the official _Spain Electric Network_ (Red Eléctrica Española, REE)
    for the _Voluntary Price for Small Consumers_
    (Precio Voluntario para el Pequeño Consumidor, PVPC).
    """
    data = xmltodict.parse(xml_data)["PVPCDesgloseHorario"]

    str_horiz = data["Horizonte"]["@v"]
    day: date = parse(str_horiz.split("/")[0]).astimezone(tz).date()

    tariff_id = f"Z0{tariff}"
    prices = next(
        filter(
            lambda x: (
                x["TerminoCosteHorario"]["@v"] == "FEU"
                and x["TipoPrecio"]["@v"] == tariff_id
            ),
            data["SeriesTemporales"],
        )
    )

    price_values = [
        round(float(pair["Ctd"]["@v"]), 5) for pair in
        prices["Periodo"]["Intervalo"]
    ]
    return day, price_values


async def async_setup_platform(
    hass, config, async_add_devices, discovery_info=None
):
    """Set up the electricity price sensor."""
    websession = async_get_clientsession(hass)
    async_add_devices(
        [
            ElecPriceSensor(
                hass,
                websession,
                config.get(CONF_NAME),
                config.get(ATTR_RATE),
                config.get(CONF_TIMEOUT),
            )
        ]
    )


class ElecPriceSensor(RestoreEntity):
    """Class to hold the prices of electricity as a sensor."""

    def __init__(self, hass, websession, name, rate, timeout):
        """Initialize the sensor object."""
        self.hass = hass
        self._websession = websession
        self._name = name
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, self._name, hass=self.hass
        )
        self.rate = rate
        self._timeout = timeout
        self._num_retries = 0
        self._state = None
        self._today_prices = None
        self._tomorrow_prices = None

        # Update 'state' value 2 times/hour
        async_track_time_change(
            self.hass, self.async_update, second=[0], minute=[0]
        )
        # Update prices at random time, 3 times/hour (don't want to upset API)
        random_minute = randint(1, 19)
        mins_update = [random_minute + 20 * i for i in range(3)]
        async_track_time_change(
            self.hass, self.async_update_prices, second=[0], minute=mins_update
        )
        _LOGGER.warning(
            f"Setup of price sensor {self.name} ({self.entity_id}) "
            f"for tariff '{self.rate}', "
            f"updating data at {mins_update} min, each hour."
        )

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            self._state = state.state
            self._today_prices = [
                state.attributes[k]
                for k in state.attributes
                if k.startswith("price")
            ]
            await self.async_update_ha_state()
        else:
            await self.async_update_prices()
            await self.async_update_ha_state(True)

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
        """Return the state attributes."""
        attributes = {ATTR_ATTRIBUTION: ATTRIBUTION, ATTR_RATE: self.rate}
        actual_hour = dt_util.now(self.hass.config.time_zone).hour
        prices = []
        if self._today_prices is not None:
            prices += self._today_prices
        if self._tomorrow_prices is not None:
            if actual_hour < 3:
                # remove 'tomorrow prices' also if updating the attrs
                self._tomorrow_prices = None
            else:
                prices += self._tomorrow_prices

        if prices:
            min_price = min(prices)
            prices_sorted = dict(
                sorted(
                    {i: p for i, p in enumerate(prices)}.items(),
                    key=lambda x: x[1],
                )
            )
            min_price_at_hour = next(iter(prices_sorted))
            next_best_at_hours = list(
                filter(lambda x: x >= actual_hour, prices_sorted.keys())
            )

            attributes["min price"] = min_price
            attributes["min price at"] = min_price_at_hour
            attributes["next best at"] = next_best_at_hours

            for i, p in enumerate(self._today_prices):
                attributes[f"price {i:02d}h"] = p
            if self._tomorrow_prices is not None:
                for i, p in enumerate(self._tomorrow_prices):
                    attributes[f"price next day {i:02d}h"] = p

        return attributes

    def _get_current_value(self, current_hour):
        """
        Quickfix to handle DST changes.
        In DST changes, there are 23 or 25 hours, so,
        adapt index accordingly.
        """
        if len(self._today_prices) == 23 and current_hour > 2:
            return self._today_prices[current_hour - 1]
        elif len(self._today_prices) == 25 and current_hour > 2:
            return self._today_prices[current_hour + 1]
        return self._today_prices[current_hour]

    async def _download_official_data(self, day: date) -> Optional[str]:
        """Make GET request to 'api.esios.ree.es' to retrieve hourly prices."""
        url = _RESOURCE.format(day=day)
        try:
            with async_timeout.timeout(self._timeout, loop=self.hass.loop):
                resp = await self._websession.get(url)
                if resp.status < 400:
                    text = await resp.text()
                    return text
                else:
                    _LOGGER.warning(
                        "Request error in '%s' [status: %d]", url, resp.status
                    )
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout error requesting data from '%s'", url)
        except aiohttp.ClientError:
            _LOGGER.error("Client error in '%s'", url)
        return None

    async def async_update(self, *_args):
        """Update the sensor state."""
        now = dt_util.now(self.hass.config.time_zone)
        if self._today_prices is not None:
            self._state = self._get_current_value(now.hour)
            await self.async_update_ha_state()
        else:
            # If no prices present, download and schedule a future state update
            self._state = None
            _LOGGER.warning(
                "Trying to update later, after %d seconds", 2 * self._timeout
            )
            async_track_point_in_time(
                self.hass,
                self.async_update,
                dt_util.now() + timedelta(seconds=2 * self._timeout),
            )
            await self.async_update_prices()

    async def async_update_prices(self, *args):
        """Update electricity prices from the ESIOS API."""
        tz = self.hass.config.time_zone
        now = args[0].astimezone(tz) if args else dt_util.now(tz)
        text = await self._download_official_data(now.date())
        if text is None:
            self._num_retries += 1
            if self._num_retries > 3:
                _LOGGER.error("Bad data update")
                return

            f_log = _LOGGER.warning if self._num_retries > 1 else _LOGGER.info
            f_log("Bad update, will try again in %d s", 3 * self._timeout)
            async_track_point_in_time(
                self.hass,
                self.async_update_prices,
                dt_util.now() + timedelta(seconds=3 * self._timeout),
            )
            return

        tariff = RATES.index(self.rate) + 1
        day, prices = extract_prices_for_tariff(text, tz, tariff)
        self._num_retries = 0
        self._today_prices = prices

        # At evening, it is possible to retrieve 'tomorrow' prices
        if now.hour >= 20:
            try:
                text_tomorrow = await self._download_official_data(
                    (now + timedelta(days=1)).date()
                )
                day_fut, prices_fut = extract_prices_for_tariff(
                    text_tomorrow, tz, tariff
                )
                _LOGGER.info(
                    "Setting tomorrow (%s) prices: %s",
                    day_fut.strftime("%Y-%m-%d"),
                    str(prices),
                )
                self._tomorrow_prices = prices_fut
                return
            except IndexError:
                _LOGGER.debug("Bad try on getting future prices")

        self._tomorrow_prices = None
