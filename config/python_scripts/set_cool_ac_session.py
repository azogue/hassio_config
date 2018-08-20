CLIMATE_ENTITY = 'climate.termostato_ac'
AUTO_OFF_ENTITY = 'automation.apagado_de_ac'
TELEGRAM_TARGET = 'sensor.telegram_default_chatid'

state_climate = hass.states.get(CLIMATE_ENTITY)
target_temp = state_climate.attributes['temperature']
current_temp = state_climate.attributes['current_temperature']

# logger.error("climate.state: %s, temperature: %s, current_temperature: %s",
#              state_climate.state, target_temp, current_temp)

if target_temp > current_temp - .5:
    # Decrease the target temp if necessary
    new_temp = target_temp - 2
    if new_temp < 26:
        new_temp = 26
    hass.services.call(
        'climate', 'set_temperature',
        {"entity_id": CLIMATE_ENTITY,
         "operation_mode": "cool",
         "temperature": new_temp})

if state_climate.state == 'off':
    # Set operation mode to cool if necessary
    hass.services.call('climate', 'set_operation_mode',
                       {"entity_id": CLIMATE_ENTITY, "operation_mode": "cool"})

# Turn on automation to turn off climate when finished
hass.services.call('automation', 'turn_on', {"entity_id": AUTO_OFF_ENTITY})

# Telegram bot notify with undo command
target = int(hass.states.get(TELEGRAM_TARGET).state)
hass.services.call(
    'telegram_bot', 'send_message',
    {"title": "*Comienzo de ciclo de AC*",
     "message": "Encendido de AC por ciclo único de enfriamiento desde "
                "{{ states.climate.termostato_ac."
                "attributes.current_temperature }} °C hasta que llegue a "
                "{{ states.climate.termostato_ac.attributes.temperature - 1}}"
                " °C (con encendido de AUTO-OFF)",
     # "target": "{{ states.sensor.telegram_default_chatid.state | int }}",
     "target": target,
     "disable_notification": True,
     "inline_keyboard": ["Deshacer:/service_call climate.set_operation_mode "
                         "termostato_ac off"]})
