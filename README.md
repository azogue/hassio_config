# Home Assistant / HASS.io personal config [![Travis Status](https://travis-ci.org/azogue/hassio_config.svg?branch=master)](https://travis-ci.org/azogue/hassio_config)

My personal [Home Assistant](https://home-assistant.io) configuration. Used for control, measure, process and automate almost everything in the house.

#### What's here

 - Control over a lot of Hue lights and one Yeelight, a Xiaomi vacuum cleaner, some IP cameras, some SONOff apliances with custom firmware, ESPHome devices, Shelly switches and meters, multiple notification components, device trackers and cloud services.
 - **A lot** of ESP32 boards running custom firmware doing lot of things like controlling lights, electrical covers, the AC or the water heater, and measuring movement, temperature, humidity, light level and even electrical power. These communicate with HA over MQTT with QOS2 messages.
 - KODI in a Nvidia Shield as the main media player, plus some chromecast devices, Sonos speakers, and more media control.
 - A QNAP NAS running multiple services (Influx, Grafana, and some custom SaaS)
 - A UPS to avoid power failures
 - More nerd stuff.
 - ...

#### How's organized

- The **[`HA`](https://www.home-assistant.io/)** instance runs Hass.io Supervisor in one dedicated, ethernet-connected, **Raspberry PI 4 4GB**, with backup power supply.
- Running as `hass.io addons` in that machine there are some other pieces of the puzzle:
  - **[AppDaemon](https://www.home-assistant.io/docs/ecosystem/appdaemon/)** running some apps like a Telegram Bot, a custom alarm clock, and much more.
  - **[Mosquitto](https://mosquitto.org/)** MQTT broker.
  - **[NGINX](https://home-assistant.io/addons/nginx_proxy/)** reverse proxy to properly access to HA and other SaaS from WAN.
- In a QNAP NAS with a x64 processor and enough RAM, with the 'Container Station' app, I run docker to exec there other precious services as:
  - **[InfluxDB](https://www.influxdata.com)** to accumulate all data the system is making (and play with it later).
  - **[Grafana](https://grafana.com)** to plot beautiful real-time graphs for everything.
  - **[MotionEye](https://github.com/ccrisan/motioneye)** to control video streams for IP cams and process motion detection on them.
  - Other databases like **MySQL** (for the Kodi Media Library) and **Mongo** (for other projects), Redis, custom SaaS and more...

Because my HomeAssistant configuration is huge, it is [splitted](https://www.home-assistant.io/docs/configuration/splitting_configuration) over multiple yaml files, and I am also using the [packages technique](https://www.home-assistant.io/docs/configuration/packages/) to group components by room, by type or even by function. You can find here examples for AppDaemon apps, python scripts, automations, custom components, an [interactive floorplan](https://github.com/pkozul/ha-floorplan) (awesome project!) and even the first tries with the new **[Lovelace UI](https://www.home-assistant.io/lovelace/)**, so, please, serve yourself.

### Screenshots

Some screenshots of the frontend:

![Home view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_1.png?raw=true)

![Kodi Control view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_2.png?raw=true)

![Weather view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_3.png?raw=true)

![Electricity view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_4.png?raw=true)


