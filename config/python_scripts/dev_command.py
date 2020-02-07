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
     - Cam Vigilia
     - Cam Reposo
     - Cam GOTO
"""
H_TARGET_VIG = 50 * 26  # 0-2600
V_TARGET_VIG = 25 * 7  # 0-700
H_TARGET_DISABLE = 2 * 26  # 0-2600
V_TARGET_DISABLE = 0

command_data = data.get("command_data", "")
command = data.get("command", "ADB command to Shield")

if command == "flash":
    try:
        flashes = int(command_data)
    except ValueError:
        flashes = 1

    hass.bus.fire(
        "flash_light",
        {
            "color": "red",
            "persistence": 1,
            "flashes": flashes,
            "lights": "light.lamparita,light.tira_larga",
        },
    )

elif command == "mqtt restart":
    logger.warning("Restarting MQTT addon!")
    hass.services.call("hassio", "addon_restart", {"addon": "a0d7b954_mqtt"})

elif command == "run in pc":
    # Example: { "command", "notepad.exe", "args": "C:\\teste.txt", "path": "C:\\", "user": "myusername" }
    # logger.warning("Run in PC: '{}'".format(command_data))
    cmds = command_data.split()
    payload = '''"command":"{}", "args":"{}", "user": "eugenio"'''.format(
        cmds[0], " ".join(cmds[1:])
    )
    payload = "{ XXX }".replace("XXX", payload)
    # logger.warning("Run in PC JSON: '{}'".format(payload))
    hass.services.call(
        "mqtt",
        "publish",
        {"topic": "iotlink/piso/w10/commands/run", "payload": payload,},
    )
    hass.services.call(
        "persistent_notification",
        "create",
        {
            "title": "Run in PC",
            "message": "## Payload:\n\n```json\n{}\n```".format(payload),
            "notification_id": "dev_command",
        },
    )

elif "cam " in command:
    if command == "cam goto":
        ht, vt, *_ = command_data.split()
        h_target = int(ht) * 26  # 0-2600
        v_target = int(vt) * 7
        switch_action = None
    elif command == "cam toggle mode":
        motion_detection_state = hass.states.get(
            "switch.motion_detection_wyzecampan1"
        )
        if motion_detection_state.state == "on":  # turn off
            h_target = H_TARGET_DISABLE
            v_target = V_TARGET_DISABLE
            switch_action = "turn_off"
        else:
            h_target = H_TARGET_VIG
            v_target = V_TARGET_VIG
            switch_action = "turn_on"
    elif command == "cam vigilia":
        h_target = H_TARGET_VIG
        v_target = V_TARGET_VIG
        switch_action = "turn_on"
    else:  # command == "cam reposo":
        h_target = H_TARGET_DISABLE
        v_target = V_TARGET_DISABLE
        switch_action = "turn_off"

    if switch_action is not None:
        hass.services.call(
            "switch",
            switch_action,
            {"entity_id": "switch.motion_detection_wyzecampan1"},
        )
        if switch_action == "turn_off":
            # Wait for it a bit
            time.sleep(2)

    hass.services.call(
        "mqtt",
        "publish",
        {
            "topic": "Domus/wyzepan1/motors/horizontal/set",
            "payload": "{}".format(h_target),
        },
    )
    hass.services.call(
        "mqtt",
        "publish",
        {
            "topic": "Domus/wyzepan1/motors/vertical/set",
            "payload": "{}".format(v_target),
        },
    )
    # hass.services.call(
    #     'cover' 'set_cover_tilt_position',
    #     {"entity_id": "cover.wyzepan1_ptc_h","tilt_position": h_target}
    # )
    # hass.services.call(
    #     'cover' 'set_cover_tilt_position',
    #     {"entity_id": "cover.wyzepan1_ptc_v", "tilt_position": v_target}
    # )
    logger.info(
        "Pan WyzeCam Tilt to position {}: {} / {}".format(
            command, h_target, v_target
        )
    )

elif "cover" in command:
    cover_esp_id = "sm1wdr811x48"
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

    logger.info("Set cover position: '{}' to {}".format(cover, position))
    hass.services.call(
        "mqtt",
        "publish",
        {
            "qos": 2,
            "retain": True,
            "topic": "smarty/{}/command/{}".format(cover_esp_id, cover),
            "payload": '{"YYY": {"command": "set_position", "value": XX }}'.replace(
                "YYY", cover
            ).replace(
                "XX", str(position)
            ),
        },
    )

elif command != "nada":
    if command == "ADB command to Shield":
        entity = "media_player.nvidia_shield"
    else:
        entity = "media_player.tv"

    # example command data: "PAUSE"
    logger.warning("Run ADB cmd: '{}' in {}".format(command_data, entity))
    hass.services.call(
        "androidtv",
        "adb_command",
        {"entity_id": entity, "command": command_data},
    )
