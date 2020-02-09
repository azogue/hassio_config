"""Python script to move WyzeCamPan."""
H_TARGET_VIG = 72 * 26  # 0-2600
V_TARGET_VIG = 1 * 7  # 0-700
H_TARGET_DISABLE = 12 * 26  # 0-2600
V_TARGET_DISABLE = 0
SWITCH_MOTION_DETECT = "switch.motion_detection_wyzecampan1"

command = data.get("command", "cam toggle mode")

if "cam " in command:
    if command == "cam goto":
        command_data = data.get("command_data", "")
        ht, vt, *_ = command_data.split()
        h_target = int(ht) * 26  # 0-2600
        v_target = int(vt) * 7
        switch_action = None
    elif command == "cam toggle mode":
        motion_detection_state = hass.states.get(SWITCH_MOTION_DETECT)
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
            "switch", switch_action, {"entity_id": SWITCH_MOTION_DETECT}
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
    logger.info(
        "Pan WyzeCam Tilt to position {}: {} / {}".format(
            command, h_target, v_target
        )
    )
