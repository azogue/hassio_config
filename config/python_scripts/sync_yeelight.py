SYNC_ORIGIN = 'light.tira'
SYNC_ENTITY = 'light.yeelight_strip_7811dca21ecf'
# SYNC_ENTITY = 'light.tira_tv'

new_state = data.get('new_state')
if new_state == 'off':
    hass.services.call('light', 'turn_off', {"entity_id": SYNC_ENTITY})
else:
    state_origin = hass.states.get(SYNC_ORIGIN)
    brightness = state_origin.attributes.get('brightness') or 100
    rgb = state_origin.attributes.get('rgb_color') or [0, 0, 255]

    logger.info("Sync Yeelight with state: %s and settings: [%s], %d",
                new_state, rgb, brightness)
    hass.services.call(
        'light', 'turn_on',
        {"entity_id": SYNC_ENTITY,
         "rgb_color": rgb, "brightness": brightness})

