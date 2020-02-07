"""
Script para encender la TV y, en función de la hora del día, poner emisión
en directo de un canal con noticias, o bien reproducir la última grabación.

# Lista canales MovistarTV en tvheadend:

        20, 'La 1 HD',
        36, 'La 2 HD',
        18, 'Antena 3 HD',
        12, 'Cuatro HD',
        13, 'Tele 5 HD',
        19, 'laSexta HD',
        25, '#0 HD',
        40, '#Vamos HD',
        39, 'À Punt',
        22, 'La Ocho Mediterráneo',
        37, 'M. FAMA 24H HD',
        7, 'FDF',
        42, 'Neox HD',
        29, 'Atreseries HD',
        9, 'Energy',
        8, 'TRECE',
        30, 'Ten',
        11, 'Paramount Network',
        23, 'DEPORTES',
        41, '#Vamos HD',
        33, 'GOL HD',
        21, 'Teledeporte HD',
        26, 'Real Madrid TV HD',
        4, 'DMAX',
        31, 'DKISS',
        5, 'Divinity',
        44, 'Nova HD',
        43, 'MEGA HD',
        28, 'BeMad HD',
        1, 'Disney Ch.',
        2, 'Boing',
        38, 'Clan TVE HD',
        6, 'Canal 24 H.',
        3, 'Intereconomía',
        32, 'Libertad Digital',
        17, 'Canal Sur Andalucía',
        16, 'Galicia TV Europa',
        34, 'Canal Extremadura SAT',
        15, 'TV3CAT',
        14, 'ETB Sat.',
        24, 'Aragón TV Int',
        10, 'LTC',
        35, 'Canal 24 H.',
        27, 'Movistar+',

"""

# Participant entities
MEDIA_PLAYER = "media_player.kodi"
ENTITY_ANDROIDTV = "media_player.tv"
INPUT_SELECT_OPTS = "input_select.kodi_results"
TELEGRAM_TARGET = "sensor.telegram_default_chatid"

# Decide what to play
now = datetime.datetime.now()
play_live_tv = True
if (now.hour < 14) or ((now.hour == 14) and (now.minute < 50)):
    content_id = 19
    media_dest = "laSexta HD"
elif now.hour < 16:
    content_id = 18
    media_dest = "Antena 3 HD"
elif now.hour < 20:
    content_id = 35
    media_dest = "Canal 24 H."
    # Last record?
    # play_live_tv = False
elif (now.hour == 20) and (now.minute < 50):
    content_id = 19
    media_dest = "laSexta HD"
elif (now.hour == 20) or ((now.hour == 21) and (now.minute < 15)):
    content_id = 18
    media_dest = "Antena 3 HD"
else:
    media_dest = "#0 HD"
    content_id = 25
    # Last record?
    # play_live_tv = False


# # Turn on Kodi with CEC
# hass.services.call(
#         'media_player', 'turn_on', {"entity_id": MEDIA_PLAYER})
tv_state = hass.states.get(ENTITY_ANDROIDTV)
if tv_state.state == "off":
    hass.services.call(
        "media_player", "turn_on", {"entity_id": ENTITY_ANDROIDTV}
    )


# Play media:
if play_live_tv:
    notify_msg = "Encendido de caja tonta en '{}'.".format(media_dest)
    hass.services.call(
        "media_player",
        "play_media",
        {
            "entity_id": MEDIA_PLAYER,
            "media_content_type": "CHANNEL",
            "media_content_id": content_id,
        },
    )
else:
    hass.services.call("script", "pvr_recordings")
    time.sleep(4)
    state_select = hass.states.get(INPUT_SELECT_OPTS)
    options = state_select.attributes.get("options")[1:] or []
    if options:
        media_dest = options[0]
        notify_msg = "Play última grabación de TV: '{}'.".format(media_dest)
        hass.services.call(
            "input_select",
            "select_option",
            {"entity_id": INPUT_SELECT_OPTS, "option": media_dest},
        )
    else:
        notify_msg = "Encendido de caja tonta en '{}'. *No hay grabaciones disponibles*".format(
            media_dest
        )
        hass.services.call(
            "media_player",
            "play_media",
            {
                "entity_id": MEDIA_PLAYER,
                "media_content_type": "CHANNEL",
                "media_content_id": content_id,
            },
        )

# Notify:
target = int(hass.states.get(TELEGRAM_TARGET).state)
hass.services.call(
    "telegram_bot",
    "send_message",
    {
        "title": "*TV PVR ON*",
        "target": target,
        "disable_notification": True,
        "message": notify_msg,
        "inline_keyboard": [
            "OFF:/service_call media_player.turn_off media_player.kodi",
            "ON:/service_call media_player.turn_on media_player.kodi",
            "‖:/service_call media_player.media_play_pause media_player.kodi",
            "◼︎:/service_call media_player.media_stop media_player.kodi",
        ],
    },
)
