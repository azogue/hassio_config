"""Python script to select target rooms to clean."""
# vacuum_clean_combination:
#     name: Selección de zona de aspirado
#     options:
#      - Nada
#      - Cocina
#      - Cocina y salón
#      - Salón
#      - Mesa de centro
#      - Zonas interiores
#      - Zona office
#      - Zona dormitorio y baño
#     initial: Nada


INPUT_SELECT = 'input_select.vacuum_clean_combination'
VACUUM_ENTITY = 'vacuum.robot_aspirador'

make_the_call = True
room_selection = data.get("room")
call_kwargs = {"entity_id": VACUUM_ENTITY, "command": "app_zoned_clean"}

if room_selection == 'Cocina':
    call_kwargs["params"] = [[23200, 24300, 28600, 25900, 2]]
elif room_selection == 'Cocina y salón':
    call_kwargs["params"] = [[23200, 24300, 28600, 25900, 1],
                             [28600, 24300, 30500, 26000, 1],
                             [30500, 24000, 35800, 28100, 1]]
elif room_selection == 'Salón':
    call_kwargs["params"] = [[30500, 24000, 35800, 28100, 2]]
elif room_selection == 'Mesa de centro':
    call_kwargs["params"] = [[33000, 24000, 36000, 26500, 2]]
elif room_selection == 'Zonas interiores':
    # Estudio + Pasillo + Baño 2 + *Pasillo dorm* + Baño dorm + dorm
    call_kwargs["params"] = [[24600, 26000, 28800, 28750, 1],
                             [28900, 26000, 29900, 29800, 1],
                             [28900, 29800, 30500, 31700, 1],
                         [30500, 28500, 36900, 31400, 1]]
elif room_selection == 'Zona office':
    call_kwargs["params"] = [[24800, 29000, 28800, 31800, 2]]
elif room_selection == 'Zona dormitorio y baño':
    call_kwargs["params"] = [[33300, 28500, 36900, 31500, 2],
                             [30500, 29800, 32600, 31400, 1]]
elif room_selection == 'Ir al salón':
    call_kwargs["command"] = "app_goto_target"
    call_kwargs["params"] = [33000, 26500]
elif room_selection == 'Ir al distribuidor':
    call_kwargs["command"] = "app_goto_target"
    call_kwargs["params"] = [29100, 29100]
elif room_selection == 'Nada':
    logger.info("No Cleaning of zone %s", room_selection)
    make_the_call = False
else:
    logger.error("ROOM not recognized: %s", room_selection)
    make_the_call = False

if make_the_call:
    hass.services.call('vacuum', 'send_command', call_kwargs)
    logger.info("Cleaning ZONE %s: %s", room_selection,
                str(call_kwargs['params']))
