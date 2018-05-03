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
#     icon: mdi:robot-vacuum
#
# Office:
# [24800, 29000, 28800, 31800]
# Dormitorio:
# [33300, 28500, 36900, 31500]
# Salón
# [30500, 24000, 36000, 28500]
#
# Mesa centro salón
# [33000, 24000, 36000, 26500]
#
# Baño dormitorio: --> BAD
# [30500, 29800, 32600, 31400]
# Hall -> check again
# [28600, 24300, 30500, 26000]
# Cocina
# [23200, 24300, 28600, 25900]
# Pasillo
# [28900, 26000, 29900, 29800]
# Pasillo dormitorio
# [29900, 28500, 33300, 29800]
# baño 2
# [28900, 29800, 30500, 31700]
# Estudio
# [24600, 26000, 28800, 28750]


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
                             [30500, 24000, 36000, 28500, 1]]
elif room_selection == 'Salón':
elif room_selection == 'Mesa de centro':
    call_kwargs["params"] = [[33000, 24000, 36000, 26500, 2]]
elif room_selection == 'Zonas interiores':
    # Estudio + Pasillo + Baño 2 + *Pasillo dorm* + Baño dorm + dorm
    call_kwargs["params"] = [[24600, 26000, 28800, 28750, 1],
                             [28900, 26000, 29900, 29800, 1],
                             [28900, 29800, 30500, 31700, 1],
                             [29900, 28500, 33300, 29800, 1],
                             [30500, 29800, 32600, 31400, 1],
                             [33300, 28500, 36900, 31500, 1]]
elif room_selection == 'Zona office':
    call_kwargs["params"] = [[24800, 29000, 28800, 31800, 2]]
elif room_selection == 'Zona dormitorio y baño':
    call_kwargs["params"] = [[33300, 28500, 36900, 31500, 2],
                             [30500, 29800, 32600, 31400, 1]]
elif room_selection == 'Nada':
    logger.info(f"No Cleaning of zone [{room_selection}]")
    make_the_call = False
else:
    logger.error("ROOM not recognized: %s", room_selection)
    make_the_call = False

if make_the_call:
    hass.services.call('vacuum', 'send_command', call_kwargs)
    logger.info(f"Cleaning ZONE {room_selection}: {call_kwargs['params']}")


# GOTO command:
# esquina_dorm
# {
#  "entity_id": "vacuum.robot_aspirador",
#  "command": "app_goto_target",
#  "params": [36000, 29000]
# }
