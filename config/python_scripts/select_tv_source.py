"""
# Python script to handle the source of TV media players.

EXAMPLE:
start_netflix:
  sequence:
  - service: media_player.select_source
    data:
      entity_id: media_player.fire_tv_living_room
      source: 'com.netflix.ninja'

stop_netflix:
  sequence:
  - service: media_player.select_source
    data:
      entity_id: media_player.fire_tv_living_room
      source: '!com.netflix.ninja'

action:
  service: androidtv.adb_command
  data:
    entity_id: media_player.androidtv_tv_living_room
    command: "HOME"
    command: "GET_PROPERTIES"

cards:
  - columns: 3
    entities:
      - entity: binary_sensor.sensor_kitchen_mov1
        name: Cocina
      - entity: binary_sensor.sensor_study_mov1
        name: Estudio
      - entity: binary_sensor.sensor_bedroom_mov1
        name: Dormitorio
    show_state: false
    type: glance

type: vertical-stack



KEYS = {"BACK": KEY_BACK,
        "BLUE": KEY_BLUE,
        "CENTER": KEY_CENTER,
        "COMPONENT1": KEY_COMPONENT1,
        "COMPONENT2": KEY_COMPONENT2,
        "COMPOSITE1": KEY_COMPOSITE1,
        "COMPOSITE2": KEY_COMPOSITE2,
        "DOWN": KEY_DOWN,
        "END": KEY_END,
        "ENTER": KEY_ENTER,
        "GREEN": KEY_GREEN,
        "HDMI1": KEY_HDMI1,
        "HDMI2": KEY_HDMI2,
        "HDMI3": KEY_HDMI3,
        "HDMI4": KEY_HDMI4,
        "HOME": KEY_HOME,
        "INPUT": KEY_INPUT,
        "LEFT": KEY_LEFT,
        "MENU": KEY_MENU,
        "MOVE_HOME": KEY_MOVE_HOME,
        "MUTE": KEY_MUTE,
        "PAIRING": KEY_PAIRING,
        "POWER": KEY_POWER,
        "RESUME": KEY_RESUME,
        "RIGHT": KEY_RIGHT,
        "SAT": KEY_SAT,
        "SEARCH": KEY_SEARCH,
        "SETTINGS": KEY_SETTINGS,
        "SLEEP": KEY_SLEEP,
        "SUSPEND": KEY_SUSPEND,
        "SYSDOWN": KEY_SYSDOWN,
        "SYSLEFT": KEY_SYSLEFT,
        "SYSRIGHT": KEY_SYSRIGHT,
        "SYSUP": KEY_SYSUP,
        "TEXT": KEY_TEXT,
        "TOP": KEY_TOP,
        "UP": KEY_UP,
        "VGA": KEY_VGA,
        "VOLUME_DOWN": KEY_VOLUME_DOWN,
        "VOLUME_UP": KEY_VOLUME_UP,
        "YELLOW": KEY_YELLOW}

options:
     - Nada
     - Youtube
     - Kodi
     - VLC
     - Prime Video
     - Movistar+
     - RTVE a la carta
     - TDT
     - Kodi RPI
     - Inmersión
     - Android TV
     - OFF
"""

INPUT_SELECT = 'input_select.tv_source'
ENTITY_ANDROIDTV = "media_player.tv"
ENTITY_SHIELD = "media_player.nvidia_shield"
ENTITY_KODI = "media_player.kodi"
ENTITY_HOMECINEMA = "media_player.home_cinema"

COVER_VENTANAL = "cover.sonoff_cover_ventanal"
COVER_PUERTA = "cover.sonoff_cover_puerta_terraza"
LIGHT_AMBILIGHT = "light.ambilight"
SWITCH_AMBILIGHT_HUE = "switch.ambilight_plus_hue"

COMMANDS = {
    "RIGHT": "RIGHT",
    "LEFT": "LEFT",
    "UP": "UP",
    "DOWN": "DOWN",
    "WAKE": "MENU",
    "SLEEP": "SLEEP",
    "ENTER": "ENTER",
    "BACK": "BACK",
    "HOME": "HOME",
    "PLAY": "input keyevent 126",
    "PAUSE": "input keyevent 127",
    "STOP": "input keyevent 86",
}

ANDROID_TV_APPS = {
    "Kodi": "am start -a android.intent.action.VIEW -d -n org.xbmc.kodi/.Splash",
    "Youtube": "am start -a android.intent.action.VIEW -d -n com.google.android.youtube.tv/com.google.android.apps.youtube.tv.activity.ShellActivity",
    "Movistar+": "am start -a android.intent.action.VIEW -d -n com.movistarplus.androidtv/.MainActivity",
    "RTVE a la carta": "am start -a android.intent.action.VIEW -d -n com.rtve.androidtv/.Screen.SplashScreen",
    "Prime Video": "am start -a android.intent.action.VIEW -d -n com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity",
}

command = data.get("source")
dest_entity = data.get(
    "entity_id",
    ENTITY_SHIELD,
)
# TODO stop active media_player in change of app/entity
logger.warning("select_tv_source: %s [%s]", command, dest_entity)

tv_state = hass.states.get(ENTITY_ANDROIDTV)
shield_state = hass.states.get(ENTITY_SHIELD)
homecinema_state = hass.states.get(ENTITY_HOMECINEMA)
# logger.warning("select_tv_source_states: %s/%s/%s", *list(map(lambda x: x.state, [tv_state, shield_state, homecinema_state])))

if tv_state.state == "off":
    hass.services.call('media_player', 'turn_on',
                       {"entity_id": ENTITY_ANDROIDTV})

if "salvapantallas" in command.lower():
    # Cast 4k video
    hass.services.call(
        # 'media_extractor', 'play_media',
        'media_player', 'play_media',
        {
            "entity_id": "media_player.shield",
            # "entity_id": "media_player.55oled803_12",
            # "media_content_id": "https://youtu.be/xGlVPzmgpSM",
            "media_content_id": "https://www.youtube.com/watch?v=Pj0w0xo2ChY&list=PL71F771F239EF17F7",
            # "media_content_id": "https://www.youtube.com/watch?v=xGlVPzmgpSM",
            # "media_content_id": "onOEns_MnC4",
            # "media_content_id": "xGlVPzmgpSM",
            "media_content_type": "video/youtube",
            # "media_content_type": "YouTube",
        }
    )
    hass.services.call(
        'input_select', 'select_option',
        {"entity_id": INPUT_SELECT, "option": "Nada"}
    )
elif command == "TDT":
    hass.services.call(
        'python_script', 'start_kodi_play_tv',
    )
    hass.services.call(
        'input_select', 'select_option',
        {"entity_id": INPUT_SELECT, "option": "Kodi"}
    )
elif command.upper() in COMMANDS.keys():
    hass.services.call(
        'androidtv', 'adb_command',
        {
            "entity_id": dest_entity,
            "command": COMMANDS[command.upper()],
        }
    )
elif command in ANDROID_TV_APPS.keys():
    #  TODO stop current playing / change source? / start tv

    hass.services.call(
        'androidtv', 'adb_command',
        {
            "entity_id": dest_entity,
            "command": ANDROID_TV_APPS[command],
        }
    )
    hass.services.call(
        'input_select', 'select_option',
        {"entity_id": INPUT_SELECT, "option": command}
    )
else:
    hass.services.call(
        'androidtv', 'adb_command',
        {
            "entity_id": dest_entity,
            "command": command,
        }
    )
