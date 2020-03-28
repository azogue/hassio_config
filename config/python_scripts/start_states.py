"""Startup script to set certain states at HA start and notify."""

# Create motioneye binary_sensors
cameras = {
    "binary_sensor.motioncam_pizero": "Vídeo-Mov. en Salón",
    "binary_sensor.motioncam_pizero2": "Vídeo-Mov. en Cocina",
    "binary_sensor.motioncam_office": "Vídeo-Mov. en Office",
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
        "message": "HA is now ready for you",
        "data": {
            "push": {"category": "CONFIRM"}
        },
    },
)
