"""
Script para encender la TV y, en función de la hora del día, poner emisión
en directo de un canal con noticias, o bien reproducir la última grabación.

# Lista canales MovistarTV en tvheadend:

        50, 'La 1 HD'
        66, 'La 2 HD'
        48, 'Antena 3 HD'
        42, 'Cuatro HD'
        43, 'Tele 5 HD'
        49, 'laSexta HD'
        55, '#0 HD'
        70, '#Vamos HD'
        69, 'À Punt'
        52, 'La Ocho Mediterráneo'
        67, 'M. FAMA 24H HD'
        37, 'FDF'
        72, 'Neox HD'
        59, 'Atreseries HD'
        39, 'Energy'
        38, 'TRECE'
        60, 'Ten'
        41, 'Paramount Network'
        53, 'DEPORTES'
        71, '#Vamos HD'
        63, 'GOL HD'
        51, 'Teledeporte HD'
        56, 'Real Madrid TV HD'
        34, 'DMAX'
        61, 'DKISS'
        35, 'Divinity'
        74, 'Nova HD'
        73, 'MEGA HD'
        58, 'BeMad HD'
        31, 'Disney Ch.'
        32, 'Boing'
        68, 'Clan TVE HD'
        36, 'Canal 24 H.'
        33, 'Intereconomía'
        62, 'Libertad Digital'
        47, 'Canal Sur Andalucía'
        46, 'Galicia TV Europa'
        64, 'Canal Extremadura SAT'
        45, 'TV3CAT'
        44, 'ETB Sat.'
        54, 'Aragón TV Int'
        40, 'LTC'
        65, 'Canal 24 H.'
        57, 'Movistar+'
        30, 'V.O.D'

"""

# Participant entities
MEDIA_PLAYER = 'media_player.kodi'
# POWER_SWITCH = 'switch.tv_power'
INPUT_SELECT_OPTS = 'input_select.kodi_results'
TELEGRAM_TARGET = 'sensor.telegram_default_chatid'

# Decide what to play
now = datetime.datetime.now()
play_live_tv = True
if (now.hour < 14) or ((now.hour == 14) and (now.minute < 50)):
    content_id = 49
    media_dest = 'La Sexta HD'
elif now.hour < 16:
    content_id = 48
    media_dest = 'Antena 3 HD'
elif now.hour < 20:
    content_id = 36
    media_dest = 'Canal 24 Horas'
    # Last record?
    # play_live_tv = False
elif (now.hour == 20) and (now.minute < 50):
    content_id = 49
    media_dest = 'La Sexta HD'
elif (now.hour == 20) or ((now.hour == 21) and (now.minute < 15)):
    content_id = 48
    media_dest = 'Antena 3 HD'
else:
    media_dest = '#0 HD'
    content_id = 55
    # Last record?
    # play_live_tv = False

# state_power = hass.states.get(POWER_SWITCH)
# if state_power.state == 'off':
#     # Need to power up TV system (and wait for it)
#     hass.services.call('switch', 'turn_on', {"entity_id": POWER_SWITCH})
#     time.sleep(5)

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
    time.sleep(4)
    state_select = hass.states.get(INPUT_SELECT_OPTS)
    options = state_select.attributes.get('options')[1:] or []
    if options:
        media_dest = options[0]
        notify_msg = "Play última grabación de TV: '{}'.".format(media_dest)
        hass.services.call(
                'input_select', 'select_option',
                {"entity_id": INPUT_SELECT_OPTS,
                 "option": media_dest})
    else:
        notify_msg = "Encendido de caja tonta en '{}'. *No hay grabaciones disponibles*".format(media_dest)
        hass.services.call(
            'media_player', 'play_media',
            {"entity_id": MEDIA_PLAYER,
             "media_content_type": "CHANNEL",
             "media_content_id": content_id})

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
