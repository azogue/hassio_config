"""Python script to select target rooms to clean.

vacuum_clean_combination:
    name: Selección de zona de aspirado
    options:
     - Nada
     - Cocina
     - Cocina y salón
     - Salón
     - Mesa de centro
     - Zonas interiores
     - Zona office
     - Zona dormitorio y baño
    initial: Nada

Call example:
  vacuum.send_command
    {
     "entity_id": "vacuum.robot_aspirador",
     "command": "app_zoned_clean",
     "params": [[28900, 29700, 30400, 31400, 1]]
    }

    {
     "entity_id": "vacuum.robot_aspirador",
     "command": "app_goto_target",
     "params": [29400, 29600]
    }

    elif room_selection == 'Ir al distribuidor':
    call_kwargs["command"] = ""
    call_kwargs["params"] = [29100, 29100]
"""

INPUT_SELECT = 'input_select.vacuum_clean_combination'
VACUUM_ENTITY = 'vacuum.robot_aspirador'

make_the_call = True
room_selection = data.get("room")
call_kwargs = {"entity_id": VACUUM_ENTITY, "command": "app_zoned_clean"}

if room_selection == 'Cocina':
    call_kwargs["params"] = [[23900, 24300, 29300, 25900, 2]]
elif room_selection == 'Cocina y salón':
    call_kwargs["params"] = [[23900, 24300, 29300, 25900, 1], [29300, 24300, 31200, 26000, 1], [31200, 24000, 36500, 28100, 1]]
elif room_selection == 'Salón':
    call_kwargs["params"] = [[31200, 24000, 36500, 28100, 2]]
elif room_selection == 'Mesa de centro':
    call_kwargs["params"] = [[33700, 24000, 36700, 26500, 2]]
elif room_selection == 'Zonas interiores':
    # TODO fix 2nd bathroom
    # Estudio + Pasillo + Baño 2 + *Pasillo dorm* + Baño dorm + dorm
    call_kwargs["params"] = [[25300, 26000, 29500, 28750, 1], [29600, 26000, 30600, 29800, 1], [29600, 29700, 31100, 31400, 1], [31200, 28500, 37600, 31400, 1]]
elif room_selection == 'Zona office':
    call_kwargs["params"] = [[25500, 29000, 29500, 31800, 2]]
elif room_selection == 'Zona dormitorio y baño':
    call_kwargs["params"] = [[34000, 28500, 37600, 31500, 2], [31200, 29800, 33300, 31400, 1]]
elif room_selection == 'Ir al salón':
    call_kwargs["command"] = "app_goto_target"
    call_kwargs["params"] = [33700, 26500]
elif room_selection == 'Ir al distribuidor':
    call_kwargs["command"] = "app_goto_target"
    call_kwargs["params"] = [29800, 29100]
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
