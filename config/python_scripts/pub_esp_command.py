"""
Python script to send a command to an ESP module via MQTT.
`python_script.pub_esp_command`

'''
{
    "topic": "smarty/sm1wdr811x48/command",
    "payload": "{\"wifi_scan\": 1}",
    "qos": 2,
    "retain": true
}
"smarty/sm1wdr811x48/command" -> {"wifi_scan": 1}
'''
"""
# msg = {"restart": 1}
# msg = {"wifi_scan": 1}
esp_name = data.get("esp_name", "sm1emkk51ehw")
command = data.get("command", "wifi_scan")

esp_names = {
    "terraza": "sm1emkk51ehw",
    "baño": "sm1wdr819nqo",
    "dormitorio": "sm1wdr80tyys",
    "galería": "sm1emkk07ot0",
    "cocina": "sm1emkk0el54",
    "salón": "sm1wdr808gow",
    "office": "sm1wdr8005r0",
    "estudio": "sm1wdr80qxj4",
    "cuadro": "sm1wdr80uy08",
    "vino": "sm1emkk51rfg",
}

msg = '{"' + command + '": 1}'
topic = "smarty/XXX/command".replace("XXX", esp_names[esp_name])
logger.warning("ESP command: {} -> {}".format(topic, command))

data_pub = {"topic": topic, "payload": msg, "qos": 2, "retain": True}
hass.services.call("mqtt", "publish", data_pub)
