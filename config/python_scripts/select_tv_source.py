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
ENTITY_HOMECINEMA = "media_player.home_cinema"

COVER_VENTANAL = "cover.sonoff_cover_ventanal"
COVER_PUERTA = "cover.sonoff_cover_puerta_terraza"
LIGHT_AMBILIGHT = "light.ambilight"
SWITCH_AMBILIGHT_HUE = "switch.ambilight_plus_hue"

scene_selection = data.get("scene")
need_reset_select = True

logger.warning("TV SOURCE select: %s.", scene_selection)

if scene_selection == 'OFF':
    # hass.services.call('media_player', 'turn_off',
    #                    {"entity_id": ENTITY_HOMECINEMA})
    hass.services.call('media_player', 'turn_off',
                       {"entity_id": ENTITY_ANDROIDTV})

elif scene_selection == 'Nada':
    need_reset_select = False

else:
    tv_state = hass.states.get(ENTITY_ANDROIDTV)

    if tv_state.state == "off":
        hass.services.call('media_player', 'turn_on',
                           {"entity_id": ENTITY_ANDROIDTV})
        time.sleep(1)

    if scene_selection == 'Youtube':
        # com.amazon.avod: "Prime Video"
        # org.xbmc.kodi: "Kodi app"
        # org.droidtv.playtv: "Raw TV"
        # com.google.android.apps.mediashell: "Google Cast"
        # com.google.android.apps.youtube: "YouTube?"
        # com.google.android.youtube.tv: "YouTube"
        # com.google.android.tvlauncher: "Android TV menu"
        # com.rtve.androidtv: "RTVE a la carta"
        # org.droidtv.settings: "Ajustes TV"
        # org.droidtv.tvsystemui: "Salvapantallas"
        # com.movistarplus.androidtv: "Movistar+"
        # #    org.videolan.vlc: "VLC"

        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_ANDROIDTV,
                            "source": "com.google.android.youtube.tv"})
    elif scene_selection == 'Kodi':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_ANDROIDTV,
                            "source": "org.xbmc.kodi"})
    elif scene_selection == 'VLC':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_ANDROIDTV,
                            "source": "org.videolan.vlc"})
    elif scene_selection == 'Prime Video':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_ANDROIDTV,
                            "source": "com.amazon.avod"})
    elif scene_selection == 'Movistar+':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_ANDROIDTV,
                            "source": "com.movistarplus.androidtv"})
    elif scene_selection == 'RTVE a la carta':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_ANDROIDTV,
                            "source": "com.rtve.androidtv"})

    elif scene_selection == 'TDT':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_HOMECINEMA,
                            "source": "Game"})

    elif scene_selection == 'Kodi RPI':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_HOMECINEMA,
                            "source": "Kodi"})

    elif scene_selection == 'Android TV':
        hass.services.call('media_player', 'select_source',
                           {"entity_id": ENTITY_ANDROIDTV,
                            "source": "com.google.android.tvlauncher"})

    elif scene_selection == 'Inmersión':
        cover_state_1 = hass.states.get(COVER_VENTANAL)
        cover_state_2 = hass.states.get(COVER_PUERTA)
        pos_cover_1 = int(cover_state_1.attributes['current_position']) if 'current_position' in cover_state_1.attributes else 0
        pos_cover_2 = int(cover_state_2.attributes['current_position']) if 'current_position' in cover_state_2.attributes else 0
        ambi_hue_state = hass.states.get(SWITCH_AMBILIGHT_HUE)

        logger.warning("Inmersion mode, now Ambi-Hue: %s, covers: V=%d, P=%d", ambi_hue_state.state, pos_cover_1, pos_cover_2)
        #     if ('current_position' in cover_state.attributes
        #             and int(cover_state.attributes['current_position']) > 40):
        #         hass.services.call('cover', 'set_cover_position',
        #                            {"entity_id": COVER_VENTANAL,
        #                             "position": 15})
        #         logger.warning("TV Night SCENE, cover_state: from %d to 15",
        #                        int(cover_state.attributes['current_position']))
        #     # hass.services.call('cover', 'set_position',
        #     #                    {"entity_id": "cover.sonoff_cover_puerta_terraza",
        #     #                     "position": 70})


        hass.services.call('switch', 'toggle',
                           {"entity_id": SWITCH_AMBILIGHT_HUE})

if need_reset_select:
    time.sleep(1)
    hass.services.call('input_select', 'select_option',
                       {"entity_id": INPUT_SELECT, "option": "Nada"})


