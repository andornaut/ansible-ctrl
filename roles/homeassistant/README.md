# ansible-role-homeassistant

An [Ansible](https://www.ansible.com/) role that provisions
[Home Assistant](https://www.home-assistant.io/) in a
[Docker](https://docs.docker.com/engine/installation/linux/docker-ce/ubuntu/) container.

## Variables

See these [default values](./defaults/main.yml).

## Integrations

* [Amcrest](https://www.home-assistant.io/integrations/amcrest/)
* [Ecobee](https://www.home-assistant.io/integrations/ecobee/)
* [Envisalink](https://www.home-assistant.io/integrations/envisalink/)
* [Foscam](https://www.home-assistant.io/integrations/foscam/)
* [HomeKit](https://www.home-assistant.io/integrations/homekit/)
* [Meross / Refoss](https://github.com/albertogeniola/meross-homeassistant)
* [Roomba](https://www.home-assistant.io/integrations/roomba/)
  * [SDK](https://github.com/koalazak/dorita980)

## Troubleshooting

### Amcrest integration: Error requesting stream: Camera is off

* [GitHub issue #55661](https://github.com/home-assistant/core/issues/55661)

*Solution*
1. Setup > Camera > Video > Sub Stream
1. Check "Enable"
1. Click "Save"
1. Restart home assistant
