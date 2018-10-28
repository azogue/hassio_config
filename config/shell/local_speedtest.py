#!/Users/uge/anaconda3/envs/py36/bin/python
"""
Speedtest script to measure periodically (and locally **) the
internet bandwitdh and publish the results in HomeAssistant as if the
speedtest sensor were running in HA.

This script runs every 10 min as is called by CRON. The crontab entry is:

```
*/10 * * * * /path/to/your/ha/config/shell/local_speedtest.py
```

** The reason for calling the speed test from a local machine instead of the
HA instance is the network quality measured by each one, as the local machine
has Giga bit ethernet and HA, in a RPI3, has not.
"""
from datetime import datetime
import json
import os

import yaml
import requests
import speedtest

# Secret config
with open(os.path.join(os.path.dirname(__file__), '..', 'secrets.yaml')) as f:
    secrets = yaml.load(f)
    long_access_token = secrets['token_speedtest']
    # ha_host = secrets['base_url']
    ha_host = secrets['weblink_hassio_lan'][:-1]
    del secrets

# Speedtest
# servers = []
speed = speedtest.Speedtest()
# speed.get_servers(servers)
speed.get_best_server()
speed.download()
speed.upload()

data = speed.results.dict()
# print(data)
# {'download': 270883081.22024065,
#  'upload': 130167872.48092493,
#  'ping': 31.153,
#  'server': {'url': 'http://speedtest.cableworld.es/speedtest/upload.php',
#            'lat': '38.4789', 'lon': '-0.7967', 'name': 'Elda',
#            'country': 'Spain', 'cc': 'ES', 'sponsor': 'Cableworld',
#            'id': '13311', 'host': 'speedtest.cableworld.es:8080',
#            'd': 31.228590889892107, 'latency': 31.153},
#  'timestamp': '2018-03-26T13:20:03.947319Z',
#  'bytes_sent': 151519232,
#  'bytes_received': 339967105,
#  'share': None,
#  'client': {'ip': '81.36.230.152', 'lat': '38.3452', 'lon': '-0.4815',
#             'isp': 'Telefonica de Espana', 'isprating': '3.7', 'rating': '0',
#             'ispdlavg': '0', 'ispulavg': '0',
#             'loggedin': '0', 'country': 'ES'}}


class JSONEncoder(json.JSONEncoder):
    """JSONEncoder that supports Home Assistant objects."""

    # pylint: disable=method-hidden
    def default(self, o):
        """Convert Home Assistant objects.

        Hand other objects to the original method.
        """
        if isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, set):
            return list(o)
        elif hasattr(o, 'as_dict'):
            return o.as_dict()

        try:
            return json.JSONEncoder.default(self, o)
        except TypeError:
            # If the JSON serializer couldn't serialize it
            # it might be a generator, convert it to a list
            try:
                return [self.default(child_obj)
                        for child_obj in o]
            except TypeError:
                # Ok, we're lost, cause the original error
                return json.JSONEncoder.default(self, o)


def set_state(entity_id, new_state, attributes, timeout=5):
    url = "{}/api/states/{}".format(ha_host, entity_id)
    headers = {
        'Authorization': "Bearer {}".format(long_access_token),
    }

    attributes = attributes or {}
    sensor_data = {'state': new_state,
                   'attributes': attributes,
                   'force_update': False}
    sensor_data = json.dumps(sensor_data, cls=JSONEncoder)

    try:
        req = requests.request(
            'POST', url, data=sensor_data, timeout=timeout,
            headers=headers)
        # print(req.text)
        if req.status_code not in (200, 201):
            print("Error changing state: %d - %s", req.status_code, req.text)
            return False
        return True
    except requests.exceptions.ConnectionError:
        print("Error connecting to server")
    except requests.exceptions.Timeout:
        error = "Timeout when talking to HA"
        print(error)
    return False


sensor_mask = 'sensor.speedtest_'
common_attrs = {
    "attribution": "Data retrieved from Speedtest by Ookla (LOCAL RUN)",
    "icon": "mdi:speedometer",
    "homebridge_hidden": True,
    "unit_of_measurement": "Mbit/s",
    "friendly_name": "Speedtest Upload",
    'bytes_sent': data['bytes_sent'],
    'bytes_received': data['bytes_received'],
    'server_country': data['server']['country'],
    'server_id': data['server']['id'],
    'latency': data['server']['latency'],
    'server_name': data['server']['name'],
}

common_attrs.update({
    "unit_of_measurement": "Mbit/s",
    "friendly_name": "Speedtest Download"
})
state_d = round(data['download'] / 1000000, 2)
set_state(sensor_mask + 'download', new_state=state_d, attributes=common_attrs)

common_attrs.update({
    "unit_of_measurement": "Mbit/s",
    "friendly_name": "Speedtest Upload"
})
state_u = round(data['upload'] / 1000000, 2)
set_state(sensor_mask + 'upload', new_state=state_u, attributes=common_attrs)

common_attrs.update({
    "unit_of_measurement": "ms",
    "friendly_name": "Speedtest Ping",
})
state_p = round(data['ping'], 1)
set_state(sensor_mask + 'ping', new_state=state_p, attributes=common_attrs)

print(f"SpeedTest Results: {state_d:.2f} / {state_u:.2f} Mbps; "
      f"{state_p:.1f} ms ping")
