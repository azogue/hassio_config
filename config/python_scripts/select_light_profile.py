"""
# Python script to select light scenes from an input_select.

Hue profiles (x, y, bright):
- relax	0.5119	0.4147	144
- energize	0.368	0.3686	203
- reading	0.4448	0.4066	240
- concentrate	0.5119	0.4147	219 <--BAD
    --> brightness: 254
        xy_color: [0.3151, 0.3251]
"""

INPUT_SELECT = "input_select.salon_light_scene"
HUE_LIGHTS_TO_CONTROL = (
    "light.bola,light.central,light.cuenco,"
    "light.pie_sofa,light.pie_tv,light.tira,light.tira_tv"
)
COVER_VENTANAL = "cover.shelly_ventanal"

scene_selection = data.get("scene")

if scene_selection == "OFF":
    hass.services.call(
        "light", "turn_off", {"entity_id": HUE_LIGHTS_TO_CONTROL}
    )
elif scene_selection == "Lectura":
    hass.services.call(
        "light",
        "turn_on",
        {"entity_id": HUE_LIGHTS_TO_CONTROL, "profile": "reading"},
    )
elif scene_selection == "Relax":
    hass.services.call(
        "light",
        "turn_on",
        {"entity_id": HUE_LIGHTS_TO_CONTROL, "profile": "relax"},
    )
elif scene_selection == "Energía":
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": HUE_LIGHTS_TO_CONTROL,
            "profile": "energize",
            "brightness": 254,
        },
    )
elif scene_selection == "Concentración":
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": HUE_LIGHTS_TO_CONTROL,
            "xy_color": [0.3151, 0.3251],
            "brightness": 254,
        },
    )

elif scene_selection == "Aurora boreal":
    hass.services.call(
        "hue",
        "hue_activate_scene",
        {"group_name": "Salón", "scene_name": "Aurora boreal"},
    )

elif scene_selection == "Flor primaveral":
    hass.services.call(
        "hue",
        "hue_activate_scene",
        {"group_name": "Salón", "scene_name": "Flor primaveral"},
    )

elif scene_selection == "Ocaso tropical":
    hass.services.call(
        "hue",
        "hue_activate_scene",
        {"group_name": "Salón", "scene_name": "Ocaso tropical"},
    )

# elif scene_selection == 'Caja tonta':
#     hass.services.call('hue', 'hue_activate_scene',
#                        {"group_name": "Salón", "scene_name": "Caja tonta"})

elif scene_selection == "Estudio":
    hass.services.call(
        "hue",
        "hue_activate_scene",
        {"group_name": "Estudio", "scene_name": "Estudiar"},
    )

elif scene_selection == "bedroom_activate_minimal":
    hass.services.call(
        "hue",
        "hue_activate_scene",
        {"group_name": "Dormitorio", "scene_name": "Minimal"},
    )

elif scene_selection == "Atardecer":
    hass.services.call(
        "hue",
        "hue_activate_scene",
        {"group_name": "Salón", "scene_name": "Atardecer en la sabana"},
    )
elif scene_selection == "TV Night":
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": "light.pie_tv",
            "xy_color": [0.156, 0.219],
            "brightness": 137,
        },
    )
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": "light.cuenco",
            "xy_color": [0.1991, 0.3772],
            "brightness": 137,
        },
    )
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": "light.bola",
            "xy_color": [0.1576, 0.2175],
            "brightness": 137,
        },
    )
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": "light.pie_sofa",
            "xy_color": [0.2356, 0.1749],
            "brightness": 137,
        },
    )
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": "light.tira,light.tira_tv",
            "xy_color": [0.2356, 0.1749],
            "brightness": 137,
        },
    )
    hass.services.call(
        "light",
        "turn_on",
        {
            "entity_id": "light.central",
            "xy_color": [0.1576, 0.2175],
            "brightness": 137,
        },
    )
    # Set cover position:
    cover_state = hass.states.get(COVER_VENTANAL)
    if (
        "current_position" in cover_state.attributes
        and int(cover_state.attributes["current_position"]) > 40
    ):
        hass.services.call(
            "cover",
            "set_cover_position",
            {"entity_id": COVER_VENTANAL, "position": 15},
        )
        logger.warning(
            "TV Night SCENE, cover_state: from %d to 15",
            int(cover_state.attributes["current_position"]),
        )
else:
    logger.error("SCENE not recognized: %s", scene_selection)
    # - Comida
    # - Cena
