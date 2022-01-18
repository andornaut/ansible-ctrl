SHELL := /bin/bash

.DEFAULT_GOAL := workstation
.PHONY: clean homeassistant-frigate nas requirements rsnapshot upgrade webservers workstation

clean:
	rm -rf .roles

homeassistant-frigate: requirements
	ansible-playbook --ask-become-pass homeassistant-frigate.yml

nas: requirements
	ansible-playbook --ask-become-pass nas.yml

requirements:
	ansible-galaxy role install -r requirements.yml
	ansible-galaxy collection install -r requirements.yml

rsnapshot: requirements
	ansible-playbook --ask-become-pass rsnapshot.yml

upgrade: requirements
	ansible-playbook --ask-become-pass upgrade.yml

webservers: requirements
	ansible-playbook --ask-become-pass webservers.yml

workstation: requirements
	ansible-playbook --ask-become-pass workstation.yml
