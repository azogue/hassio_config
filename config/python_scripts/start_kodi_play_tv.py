"""
Script para encender la TV y, en función de la hora del día, poner emisión
en directo de un canal con noticias, o bien reproducir la última grabación.

# Lista canales MovistarTV en tvheadend:
        10, 'La 2',
        33, 'Antena 3 HD',
        42, 'Cuatro HD',
        44, 'Telecinco HD',
        18, 'La Sexta HD',
        55, '#0 HD',
        29, 'TV Mediterráneo ',
        52, 'TV3 HD ',
        17, 'FDF',
        6, 'Neox',
        8, 'Atreseries HD',
        41, 'Energy',
        4, 'Ten',
        7, 'Paramount Channel',
        34, 'DEPORTES HD',
        31, 'Teledeporte',
        57, 'Teledeporte HD',
        58, 'Discovery Max',
        49, 'DKISS ',
        19, 'Divinity',
        43, 'Nova',
        39, 'MEGA',
        16, 'Disney Channel HD',
        9, 'Boing',
        2, 'Clan TVE',
        20, '24 Horas',
        5, 'Xarxa Televisions ',
        1, 'Movistar+ HD',
"""

# Participant entities
MEDIA_PLAYER = 'media_player.kodi'
POWER_SWITCH = 'switch.tv_power'
INPUT_SELECT_OPTS = 'input_select.kodi_results'
TELEGRAM_TARGET = 'sensor.telegram_default_chatid'

# Decide what to play
now = datetime.datetime.now()
play_live_tv = True
if (now.hour < 14) or ((now.hour == 14) and (now.minute < 50)):
    content_id = 18
    media_dest = 'La Sexta HD'
elif now.hour < 16:
    content_id = 33
    media_dest = 'Antena 3 HD'
elif now.hour < 20:
    content_id = 20
    media_dest = '24 Horas'
    # Last record?
    play_live_tv = False
elif (now.hour == 20) and (now.minute < 50):
    content_id = 18
    media_dest = 'La Sexta HD'
elif (now.hour == 20) or ((now.hour == 21) and (now.minute < 15)):
    content_id = 33
    media_dest = 'Antena 3 HD'
else:
    media_dest = '#0 HD'
    content_id = 55
    # Last record?
    play_live_tv = False

state_power = hass.states.get(POWER_SWITCH)
if state_power.state == 'off':
    # Need to power up TV system (and wait for it)
    hass.services.call('switch', 'turn_on', {"entity_id": POWER_SWITCH})
    time.sleep(5)

# Turn on Kodi with CEC
hass.services.call(
        'media_player', 'turn_on', {"entity_id": MEDIA_PLAYER})

# Play media:
if play_live_tv:
    notify_msg = "Encendido de caja tonta en '{}'.".format(media_dest)
    hass.services.call(
        'media_player', 'play_media',
        {"entity_id": MEDIA_PLAYER,
         "media_content_type": "CHANNEL",
         "media_content_id": content_id})
else:
    hass.services.call('script', 'pvr_recordings')
    time.sleep(3)
    state_select = hass.states.get(INPUT_SELECT_OPTS)
    options = state_select.attributes.get('options')[1:] or []
    media_dest = options[0]
    notify_msg = "Play última grabación de TV: '{}'.".format(media_dest)
    hass.services.call(
            'input_select', 'select_option',
            {"entity_id": INPUT_SELECT_OPTS,
             "option": media_dest})

# Notify:
target = int(hass.states.get(TELEGRAM_TARGET).state)
hass.services.call(
        'telegram_bot', 'send_message',
        {"title": '*TV PVR ON*',
         "target": target,
         "disable_notification": True,
         "message": notify_msg,
         "inline_keyboard": ['OFF:/service_call media_player.turn_off media_player.kodi',
                             'ON:/service_call media_player.turn_on media_player.kodi',
                             '‖:/service_call media_player.media_play_pause media_player.kodi',
                             '◼︎:/service_call media_player.media_stop media_player.kodi']})
