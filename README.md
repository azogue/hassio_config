# Home Assistant / HASS.io personal config [![Travis Status](https://travis-ci.org/azogue/hassio_config.svg?branch=master)](https://travis-ci.org/azogue/hassio_config)

<img src="https://github.com/azogue/hassio_config/blob/master/screenshots/addons_and_services_schema.png?raw=true" width="100%" height="100%">

------------------------------------------------------------------------
My personal [Home Assistant](https://home-assistant.io) configuration. Used for control, measure, process and automate almost everything in the house.

#### What's here

 - Control over a lot of Hue lights and one Yeelight, a bunch of Etekcity RF outlets, a Xiaomi vacuum cleaner, some IP cameras, some SONOff apliances with custom firmware, multiple notification components, device trackers and cloud services.
 - **A lot** of ESP32 boards running custom firmware doing lot of things like controlling lights, electrical covers, the AC or the water heater, and measuring movement, temperature, humidity, light level and even electrical power. These communicate with HA over MQTT with QOS2 messages.
 - KODI in a RPI3b+ (LibreElec flavour) controlling the TV and the Home cinema over CEC.
 - A QNAP NAS with Container Station (:= docker) running multiple services (Influx, Grafana, Pi-hole and some custom SaaS)
 - More nerd stuff.
 - ...

#### How's organized

- The **[`hass.io`](https://www.home-assistant.io/hassio/)** instance runs in one dedicated, ethernet-connected, **Raspberry PI 3**, with some sensors attached and backup power supply.
- Running as `hass.io addons` in that machine there are some other pieces of the puzzle:
  - **[AppDaemon](https://www.home-assistant.io/docs/ecosystem/appdaemon/)** running some apps like a Telegram Bot, a custom alarm clock, and much more.
  - **[Homebridge](https://github.com/nfarina/homebridge)** to publish some of the HA entities to HomeKit and talk to the house.
  - LAN access to the machine via secure **SSH** and authorized Samba.
  - **[Let's Encrypt](https://letsencrypt.org/)** certs with NO-IP service for WAN public access.
  - **[Mosquitto](https://mosquitto.org/)** MQTT broker.
  - **[NGINX](https://home-assistant.io/addons/nginx_proxy/)** reverse proxy to properly access to HA and other SaaS from WAN.
- In a QNAP NAS with a x64 processor and enough RAM, with the 'Container Station' app, I run docker to exec there other precious services as:
  - **[InfluxDB](https://www.influxdata.com)** to accumulate all data the system is making (and play with it later).
  - **[Grafana](https://grafana.com)** to plot beautiful real-time graphs for everything.
  - **[MotionEye](https://github.com/ccrisan/motioneye)** to control video streams for IP cams and process motion detection on them.
  - Other databases like **MySQL** (for the Kodi Media Library) and **Mongo** (for other projects), Redis, custom SaaS and more...

There are many addons that could just run in the little RPI3, but for SD endurance I prefer to outsource some. Next step for HA/Hass.io has to be docker swarm compatibility!

Because my HomeAssistant configuration is huge, it is [splitted](https://www.home-assistant.io/docs/configuration/splitting_configuration) over multiple yaml files, and I am also using the [packages technique](https://www.home-assistant.io/docs/configuration/packages/) to group components by room, by type or even by function. You can find here examples for AppDaemon apps, python scripts, automations, custom components, an [interactive floorplan](https://github.com/pkozul/ha-floorplan) (awesome project!) and even the first tries with the new **[Lovelace UI](https://www.home-assistant.io/lovelace/)**, so, please, serve yourself.

### Screenshots

Some screenshots of the frontend:

![Home view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_1.png?raw=true)

![Kodi Control view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_2.png?raw=true)

![Weather view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_3.png?raw=true)

![Electricity view](https://github.com/azogue/hassio_config/blob/master/screenshots/screenshot_4.png?raw=true)


