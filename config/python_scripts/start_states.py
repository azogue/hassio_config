"""
# Startup script

Python script to set certain states at HA start and notify.
This unifies various automations and HA scripts in a simpler one.

"""

# Create motioneye binary_sensors
cameras = {
    "binary_sensor.motioncam_pizero": "Vídeo-Mov. en PIzero",
    "binary_sensor.motioncam_pizero2": "Vídeo-Mov. en PIW2",
    # 'binary_sensor.motioncam_office': "Vídeo-Mov. en Office",
}
for bs, fn in cameras.items():
    hass.states.set(
        bs, "off", attributes={"friendly_name": fn, "device_class": "motion"}
    )

# Notify HA init with iOS
hass.services.call(
    "notify",
    "mobile_app_iphone",
    {
        "title": "Home-assistant started",
        "message": "Hassio is now ready for you",
        "data": {
            "push": {
                "badge": 5,
                "sound": "US-EN-Morgan-Freeman-Welcome-Home.wav",
                "category": "CONFIRM",
            }
        },
    },
)
