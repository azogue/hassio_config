SYNC_ORIGIN = 'light.tira'
SYNC_ENTITY = 'light.yeelight_strip_7811dca21ecf'
# SYNC_ENTITY = 'light.tira_tv'

new_state = data.get('new_state')
if new_state == 'off':
    hass.services.call('light', 'turn_off', {"entity_id": SYNC_ENTITY})
else:  # has to be 'on' (automation triggers)
    state_origin = hass.states.get(SYNC_ORIGIN)
    brightness = state_origin.attributes.get('brightness') or 100
    #rgb = state_origin.attributes.get('rgb_color') or [0, 0, 255]
    xy = state_origin.attributes.get('xy_color') or [0.1576, 0.2175]

    logger.info("Sync Yeelight with state: %s and settings: [%s], %d",
                new_state, xy, brightness)
    hass.services.call(
        'light', 'turn_on',
        {"entity_id": SYNC_ENTITY,
         "xy_color": xy, "brightness": brightness})
         # "rgb_color": rgb, "brightness": brightness})

