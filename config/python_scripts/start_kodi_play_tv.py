"""
Script para encender la TV y, en función de la hora del día, poner emisión
en directo de un canal con noticias, o bien reproducir la última grabación.

# Lista canales MovistarTV en tvheadend:

		33, 'La 1 HD',
		50, 'La 1',
		8, 'La 2 HD',
		35, 'La 2',
		46, 'Antena 3',
		26, 'Antena 3 HD',
		2, 'Cuatro',
		9, 'Cuatro HD',
		25, 'Telecinco',
		63, 'Telecinco HD',
		18, 'La Sexta',
		41, 'La Sexta HD',
		61, '#0',
		66, '#0 HD',
		31, '#Vamos',
		11, '#Vamos HD',
		57, 'À Punt',
		5, 'Canal Sur 1 HD',
		24, 'TV3 HD',
		58, 'TV Mediterráneo',
		53, 'Castilla la Mancha TV',
		56, '7 TV Región Murcia',
		1, 'FDF',
		20, 'Neox',
		37, 'Atreseries',
		64, 'Atreseries HD',
		19, 'Energy',
		42, '13 TV',
		55, 'Ten',
		17, 'Paramount Network',
		29, 'DEPORTES',
		30, 'DEPORTES HD',
		16, 'M. eSports HD',
		4, 'M. eSports',
		27, 'GOL',
		62, 'GOL HD',
		60, 'Teledeporte',
		6, 'Teledeporte HD',
		14, 'Real Madrid TV',
		39, 'Real Madrid TV HD',
		48, 'Discovery Max',
		36, 'DKISS',
		47, 'Divinity',
		34, 'Nova',
		15, 'MEGA',
		28, 'BeMad',
		10, 'BeMad HD',
		49, 'Disney Channel',
		23, 'Disney Channel HD',
		59, 'Boing',
		32, 'Clan TVE',
		45, 'Clan TVE HD',
		51, 'Canal 24 Horas',
		65, 'Intereconomía TV',
		13, 'Libertad Digital',
		12, 'Canal Sur Andalucía',
		40, 'Galicia TV Europa',
		7, 'Canal Extremadura SAT',
		22, 'TV3CAT',
		21, 'ETB Sat',
		44, 'Aragón TV Int',
		38, 'Betevé',
		54, 'LaLiga 123 TV Multi 1',
		43, 'La Tienda en Casa',
		52, 'beIN LaLiga 4K DRM',
		3, 'LaLiga TV Bar HD',

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
    content_id = 41
    media_dest = 'La Sexta HD'
elif now.hour < 16:
    content_id = 26
    media_dest = 'Antena 3 HD'
elif now.hour < 20:
    content_id = 51
    media_dest = 'Canal 24 Horas'
    # Last record?
    # play_live_tv = False
elif (now.hour == 20) and (now.minute < 50):
    content_id = 41
    media_dest = 'La Sexta HD'
elif (now.hour == 20) or ((now.hour == 21) and (now.minute < 15)):
    content_id = 26
    media_dest = 'Antena 3 HD'
else:
    media_dest = '#0 HD'
    content_id = 66
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
