"""Stock market information from Finnhub."""
from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_API_KEY, CONF_CURRENCY, CONF_NAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import finnhub
import time
import datetime

_LOGGER = logging.getLogger(__name__)

ATTR_CLOSE = "close"
ATTR_HIGH = "high"
ATTR_LOW = "low"
ATTR_CHANGE = "change"
ATTR_PERCENT_CHANGE = "percentChange"
ATTR_CURRENT = "current"
ATTR_OPEN = "open"
ATTR_PREVIOUS_CLOSE = "previousClose"
ATTR_TIMESTAMP = "timestamp"
ATTR_52_WEEK_LOW = "52WeekLow"
ATTR_52_WEEK_LOW_DATE = "52WeekLowDate"
ATTR_52_WEEK_HIGH = "52WeekHigh"
ATTR_52_WEEK_HIGH_DATE = "52WeekHighDate"
ATTR_ALERT_INFO = "alertInfo"

FINNHUB_QUOTE = "quote"
FINNHUB_BASIC_FINANCIALS = "basic_financials"
FINNHUB_METRIC = "metric"


ATTRIBUTION = "Stock market information provided by Finnhub"

CONF_FOREIGN_EXCHANGE = "foreign_exchange"
CONF_FROM = "from"
CONF_SYMBOL = "symbol"
CONF_SYMBOLS = "symbols"
CONF_TO = "to"
CONF_RISING_THRESHOLD = "rising_threshold"
CONF_FALLING_THRESHOLD = "falling_threshold"

ICONS = {
    "BTC": "mdi:currency-btc",
    "EUR": "mdi:currency-eur",
    "GBP": "mdi:currency-gbp",
    "INR": "mdi:currency-inr",
    "RUB": "mdi:currency-rub",
    "TRY": "mdi:currency-try",
    "USD": "mdi:currency-usd",
}

SCAN_INTERVAL = timedelta(minutes=5)

SYMBOL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SYMBOL): cv.string,
        vol.Optional(CONF_CURRENCY): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_RISING_THRESHOLD): int,
        vol.Optional(CONF_FALLING_THRESHOLD): int,
    }
)

CURRENCY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FROM): cv.string,
        vol.Required(CONF_TO): cv.string,
        vol.Optional(CONF_NAME): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_FOREIGN_EXCHANGE): vol.All(cv.ensure_list, [CURRENCY_SCHEMA]),
        vol.Optional(CONF_SYMBOLS): vol.All(cv.ensure_list, [SYMBOL_SCHEMA]),
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Finnhub sensor."""
    api_key = config[CONF_API_KEY]
    symbols = config.get(CONF_SYMBOLS, [])

    if not symbols:
        msg = "No symbols or currencies configured."
        persistent_notification.create(hass, msg, "Sensor finnhub")
        _LOGGER.warning(msg)
        return

    finnhub_client = finnhub.Client(api_key=api_key)

    dev: list[SensorEntity] = []
    for symbol in symbols:
        dev.append(FinnhubSensor(hass, api_key, symbol))

    add_entities(dev, True)
    _LOGGER.debug("Setup completed")


class FinnhubSensor(SensorEntity):
    _attr_attribution = ATTRIBUTION

    def __init__(self, hass: HomeAssistant, api_key: str, symbol: dict):
        """Initialize the sensor."""
        self.hass = hass
        self._api_key = api_key
        self._symbol = symbol[CONF_SYMBOL]
        self._attr_name = symbol.get(CONF_NAME, self._symbol)
        self._attr_native_unit_of_measurement = symbol.get(CONF_CURRENCY, "USD")
        self._attr_icon = ICONS.get(symbol.get(CONF_CURRENCY, "USD"))
        _LOGGER.info('symbol is {}'.format(symbol))
        self._attr_rising_threshold: int = symbol[CONF_RISING_THRESHOLD]
        self._attr_falling_threshold: int = symbol[CONF_FALLING_THRESHOLD]

    def __get_today_start_timestamp(self):
        today = datetime.date.today()
        today_start_time = int(time.mktime(time.strptime(str(today), '%Y-%m-%d')))
        return today_start_time
    
    def update(self) -> None:
        """Get the latest data and updates the states."""
        _LOGGER.debug("Requesting new data for symbol %s", self._symbol)
        
        finnhub_client = finnhub.Client(api_key=self._api_key)
        result = {}
        try:
            _LOGGER.debug("Configuring timeseries for symbols: %s", self._symbol)
            result[FINNHUB_QUOTE] = finnhub_client.quote(self._symbol)
            result[FINNHUB_BASIC_FINANCIALS] = finnhub_client.company_basic_financials(self._symbol, 'all')[FINNHUB_METRIC]
        except ValueError:
            _LOGGER.error("API Key is not valid or symbol '%s' not known", self._symbol)
            return
        
        values = result[FINNHUB_QUOTE]
        basic_financials = result[FINNHUB_BASIC_FINANCIALS]
        
        # if isinstance(values, dict) and "c" in values:
        #     self._attr_native_value = values["c"]
        # else:
        #     self._attr_native_value = None
        
        if isinstance(values, dict) and isinstance(basic_financials, dict):
            high = values["h"]
            low = values["l"]
            change = values["d"]
            percent_change = values["dp"]
            current = values["c"]
            open_price = values["o"]
            previous_close = values["pc"]
            timestamp = values["t"]
            low_52_week = basic_financials[ATTR_52_WEEK_LOW]
            high_52_week = basic_financials[ATTR_52_WEEK_HIGH]
            low_52_week_date = basic_financials[ATTR_52_WEEK_LOW_DATE]
            high_52_week_date = basic_financials[ATTR_52_WEEK_HIGH_DATE]
            alert_info = None
            b_need_alert = False
            if(current > 0):
                if(current < low_52_week):
                    b_need_alert = True
                    alert_info = "{} is below 52 week low".format(self._symbol)
                elif(high_52_week > 0 and current > high_52_week):
                    b_need_alert = True
                    alert_info = "{} is above 52 week high".format(self._symbol)
                elif(low > 0 and current > low):
                    if(current - low) / current * 100 >= self._attr_rising_threshold:
                        b_need_alert = True
                        alert_info = "{} is rising above {}%".format(self._symbol, self._attr_rising_threshold)
                elif(current < high):
                    if(high - current) / high * 100 >= self._attr_falling_threshold:
                        b_need_alert = True
                        alert_info = "{} is falling above {}%".format(self._symbol, self._attr_falling_threshold)
            
            if(b_need_alert):
                self._attr_native_value = self.__get_today_start_timestamp()
            
            if(alert_info != None):
                _LOGGER.info('got alert info is {}'.format(alert_info))
                await hass.bus.async_fire(EVENT_STATE_CHANGED, event_data, EventOrigin.local)

            self._attr_extra_state_attributes = ({
                ATTR_HIGH: high,
                ATTR_LOW: low,
                ATTR_CHANGE: change,
                ATTR_PERCENT_CHANGE: percent_change,
                ATTR_CURRENT: current,
                ATTR_OPEN: open_price,
                ATTR_PREVIOUS_CLOSE: previous_close,
                ATTR_TIMESTAMP: timestamp,
                ATTR_52_WEEK_LOW: low_52_week,
                ATTR_52_WEEK_LOW_DATE: low_52_week_date,
                ATTR_52_WEEK_HIGH: high_52_week,
                ATTR_52_WEEK_HIGH_DATE: high_52_week_date,
                ATTR_ALERT_INFO: alert_info,
            })
        else:
            self._attr_extra_state_attributes = {}
            
        _LOGGER.debug("Received new values for symbol %s, value is %s", self._symbol, self._attr_extra_state_attributes)
