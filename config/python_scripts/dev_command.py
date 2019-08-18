"""Python script to do stuff

input_select:
  dev_command:
    name: Comandos avanzados
    options:
     - Nada
     - Flash
     - ADB command to Shield
     - ADB command to TV
     - Cover ventanal 100
     - Cover puerta 100
     - Run in PC
     - MQTT restart

"""
command_data = data.get('command_data', '')
command = data.get('command', 'ADB command to Shield')

logger.error("DEV command: {} -> {}".format(command, command_data))

if command == "flash":
    try:
        flashes = int(command_data)
    except ValueError:
        flashes = 1

    hass.bus.fire(
        'flash_light',
        {
            "color": "red",
            "persistence": 1,
            "flashes": flashes,
            "lights": "light.lamparita,light.tira_larga",
        }
    )

elif command == "mqtt restart":
    logger.warning("Restarting MQTT addon!")
    hass.services.call('hassio', 'addon_restart', {"addon": "a0d7b954_mqtt"})

elif command == "run in pc":
    # Example: { "command", "notepad.exe", "args": "C:\\teste.txt", "path": "C:\\", "user": "myusername" }
    # logger.warning("Run in PC: '{}'".format(command_data))
    cmds = command_data.split()
    payload = '''"command":"{}", "args":"{}", "user": "eugenio"'''.format(cmds[0], ' '.join(cmds[1:]))
    payload = '{ XXX }'.replace("XXX", payload)
    # logger.warning("Run in PC JSON: '{}'".format(payload))
    hass.services.call(
        'mqtt', 'publish',
        {
            "topic": "iotlink/piso/w10/commands/run",
            "payload": payload,
        }
    )
    hass.services.call(
        'persistent_notification', 'create',
        {
            "title": 'Run in PC',
            "message": "## Payload:\n\n```json\n{}\n```".format(payload),
            "notification_id": "dev_command",
        }
    )

elif "cover" in command:
    cover_esp_id = 'sm1wdr811x48'
    # - Cover ventanal 100
    # - Cover puerta 100
    if "ventanal" in command:
        cover = "cover1"
    else:
        cover = "cover2"

    try:
        position = int(command_data)
    except ValueError:
        position = 100

    logger.warning("Set cover position: '{}' to {}".format(cover, position))
    hass.services.call(
        'mqtt', 'publish',
        {
            "qos": 2,
            "retain": True,
            "topic": "smarty/{}/command/{}".format(cover_esp_id, cover),
            "payload": '{"YYY": {"command": "set_position", "value": XX }}'.replace('YYY', cover).replace('XX', str(position)),
        }
    )

elif command != "nada":
    if command == "ADB command to Shield":
        entity = "media_player.nvidia_shield"
    else:
        entity = "media_player.tv"

    # example command data: "PAUSE"
    logger.warning("Run ADB cmd: '{}' in {}".format(command_data, entity))
    hass.services.call(
        'androidtv', 'adb_command',
        {"entity_id": entity, "command": command_data}
    )
