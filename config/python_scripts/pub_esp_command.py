"""Python script to send a command to an ESP module via MQTT."""
# python_script.pub_esp_command

# msg = {"restart": 1}
# msg = {"wifi_scan": 1}
esp_name = data.get('esp_name', 'sm1emkk51ehw')
command = data.get('command', 'wifi_scan')  # '' restart

esp_names = {
    "terraza": "sm1emkk51ehw",
    "baño": "sm1wdr819nqo",
    "dormitorio": "sm1wdr80tyys",
    "persianas": "sm1wdr811x48",
    "galeria": "sm1emkk07ot0",
    "hall": "sm1emkk0h98o",
    "cocina": "sm1emkk0el54",
    "salón": "sm1wdr808gow",
    "office": "sm1wdr8005r0",
    "estudio": "sm1wdr80qxj4",
    "cuadro": "sm1wdr80uy08",
    "vino": "sm1emkk51rfg",
}

msg = '{\"' + command + '\": 1}'
topic = 'smarty/XXX/command'.replace('XXX', esp_names[esp_name])
if esp_name == 'persianas':
    topic = topic + '/cover1'
logger.error("ESP command: {} -> {}".format(topic, command))

# '''
# {
#     "topic": "smarty/sm1wdr811x48/command",
#     "payload": "{\"wifi_scan\": 1}",
#     "qos": 2,
#     "retain": true
# }
# "smarty/sm1wdr811x48/command" -> {"wifi_scan": 1}
# '''
data_pub = {
    "topic": topic,
    "payload": msg,
    "qos": 2,
    "retain": True
}
hass.services.call('mqtt', 'publish', data_pub)
logger.error("AFTER ESP command: {} -> {}".format(topic, msg))
