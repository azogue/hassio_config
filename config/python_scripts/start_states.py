"""
# Startup script

Python script to set certain states at HA start and notify.
This unifies various automations and HA scripts in a simpler one.

"""

# Anyone at home?
family_home = hass.states.get('group.family').state == 'home'

# Turn on default outlets
if family_home:
    hass.services.call(
        'switch', 'turn_on',
        {"entity_id": "switch.tv_power,switch.camara,switch.vinoteca"})
        # {"entity_id": "switch.calentador,switch.bomba_circ_acs"})

# Create motioneye binary_sensors
cameras = {
    'binary_sensor.motioncam_salon': "Vídeo-Mov. en Salón",
    'binary_sensor.motioncam_terraza': "Vídeo-Mov. en Terraza",
    'binary_sensor.motioncam_office': "Vídeo-Mov. en Estudio",
}
for bs, fn in cameras.items():
    hass.states.set(bs, 'off',
                    attributes={
                        "friendly_name": fn,
                        "homebridge_hidden": "true",
                        "device_class": "motion"})

# Sync HA dev trackers with manual HomeKit input_booleans
dev_tracking = {'group.eugenio': 'input_boolean.eu_presence',
                'group.mary': 'input_boolean.carmen_presence'}
for group in dev_tracking:
    input_b = dev_tracking.get(group)
    b_in_home = hass.states.get(group).state == 'home'
    input_b_st = hass.states.get(input_b)
    input_b_in_home = input_b_st.state == 'on'
    if input_b_in_home != b_in_home:
        logger.warning('SYNC error %s: dev_tracker=%s, HomeKit=%s',
                       group.lstrip('group.'), b_in_home, input_b_in_home)
        hass.states.set(input_b, "on" if b_in_home else "off",
                        attributes=input_b_st.attributes)

# Notify HA init with iOS
hass.services.call(
    'notify', 'ios_iphone',
    {"title": "Home-assistant started",
     "message": "Hass is now ready for you",
     "data": {"push": {"badge": 5,
                       "sound": "US-EN-Morgan-Freeman-Welcome-Home.wav",
                       "category": "CONFIRM"}}})
