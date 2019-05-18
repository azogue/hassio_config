"""Python script to run when some IFTTT event is received.

```json
{
    "motion": "on",
    "message": "Motion alarm detected on WyzeCam2 ",
    "ts": "May 11, 2019 at 02:52PM",
    "webhook_id": "...."
}

{"data": {
    "motion": "on",
    "message": "Motion alarm detected on WyzeCam2 ",
    "ts": "May 11, 2019 at 02:52PM",
    "webhook_id": "...."
}}
```

"""

message = data.get("message")
logger.warning("DEBUG message: %s", message)

if message == "RESET":
    bin_sensor_entity_id = data.get("entity_id")
    hass.states.set(
        bin_sensor_entity_id, "off",
        # attributes={
        #     "friendly_name": "Vídeo-Mov. en " + wyze_cam,
        #     "device_class": "motion"
        # }
    )
else:
    wyze_cam = message.strip().split()[-1]

    logger.warning("Wyze motion detected in %s", wyze_cam)

    hass.states.set(
        "binary_sensor.motioncam_" + wyze_cam.lower(), "on",
        attributes={
            "friendly_name": "Vídeo-Mov. en " + wyze_cam,
            "device_class": "motion"
        }
    )
    hass.bus.fire(
        'flash_light',
        {
            "color": "red",
            "persistence": 1,
            "flashes": 1,
            "lights": "light.lamparita,light.cuenco",
        }
    )

#
# else:
#     hass.bus.fire(
#         'flash_light',
#         {
#             "color": "violet",
#             "persistence": 1,
#             "flashes": 3,
#             "lights": "light.lamparita",
#         }
#     )
#     logger.warning("IFTTT event received: %s", data)
