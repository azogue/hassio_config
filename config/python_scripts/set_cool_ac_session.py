"""
climate.calefaccion	    off
    hvac_modes: heat,off
    current_temperature: 25.4
    min_temp: 16
    max_temp: 27
    temperature: 18
    hvac_action: off
    preset_mode: null
    preset_modes: away
    friendly_name: Calefacción
    supported_features: 17

climate.termostato_ac	cool
    hvac_modes: cool,off
    current_temperature: 25.4
    min_temp: 18
    max_temp: 30
    temperature: 26
    hvac_action: cooling

"""
operation_mode = data.get("mode")
cool_mode = operation_mode == 'cool'

entity_name = 'termostato_ac' if cool_mode else 'calefaccion'
CLIMATE_ENTITY = 'climate.' + entity_name
AUTO_OFF_ENTITY = 'automation.apagado_de_ac'
TELEGRAM_TARGET = 'sensor.telegram_default_chatid'

state_climate = hass.states.get(CLIMATE_ENTITY)
target_temp = state_climate.attributes['temperature']
current_temp = state_climate.attributes['current_temperature']

# logger.error("climate.state: %s, temperature: %s, current_temperature: %s",
#              state_climate.state, target_temp, current_temp)

if target_temp > current_temp - .5 and entity_name == 'termostato_ac':
    # Decrease the target temp if necessary
    new_temp = target_temp - 2
    if new_temp < 24:
        new_temp = 24
    hass.services.call(
        'climate', 'set_temperature',
        {"entity_id": CLIMATE_ENTITY,
         "hvac_mode": operation_mode,
         "temperature": new_temp})

if state_climate.state == 'off':
    # Set operation mode to cool if necessary
    hass.services.call('climate', 'set_hvac_mode',
                       {"entity_id": CLIMATE_ENTITY,
                        "hvac_mode": operation_mode})

# Turn on automation to turn off climate when finished
hass.services.call('automation', 'turn_on', {"entity_id": AUTO_OFF_ENTITY})

message = ("Encendido de AC por ciclo único de calentamiento desde "
           "{{ states.climate.calefaccion."
           "attributes.current_temperature }} °C hasta que llegue a "
           "{{ states.climate.calefaccion.attributes.temperature + 1}}"
           " °C (con encendido de AUTO-OFF)")
if cool_mode:
    message = (message
               .replace(' + 1', ' - 1')
               .replace('calefaccion', 'termostato_ac')
               .replace('calentamiento', 'enfriamiento'))

# Telegram bot notify with undo command
target = int(hass.states.get(TELEGRAM_TARGET).state)
hass.services.call(
    'telegram_bot', 'send_message',
    {"title": "*Comienzo de ciclo de AC*",
     "message": message,
     # "target": "{{ states.sensor.telegram_default_chatid.state | int }}",
     "target": target,
     "disable_notification": True,
     "inline_keyboard": ["Deshacer:/service_call climate.set_hvac_mode "
                         + entity_name + " off"]})
