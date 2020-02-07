"""Python script to set the default chat id for the Telegram Bot."""
SENSOR_CHATID = "sensor.telegram_default_chatid"
SENSOR_ATTRS = {
    "friendly_name": "Telegram default chatID",
    "icon": "mdi:telegram",
}

last_chat_id = hass.states.get(SENSOR_CHATID)
chat_id = int(data.get("chat_id"))

if chat_id is not None:
    if last_chat_id is None:  # Init
        logger.debug("Telegram default chat_id: %s", chat_id)
        hass.states.set(SENSOR_CHATID, chat_id, attributes=SENSOR_ATTRS)
    else:
        last_chat_id = int(last_chat_id.state)
        if last_chat_id != chat_id:
            logger.info("Telegram chat_id: %s -> %s", last_chat_id, chat_id)
            hass.states.set(SENSOR_CHATID, chat_id, attributes=SENSOR_ATTRS)
else:
    logger.warning("Telegram new chat_id: %s!", chat_id)
