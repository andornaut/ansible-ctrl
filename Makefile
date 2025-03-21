SHELL := /bin/bash

.DEFAULT_GOAL := workstation

# Mark targets that don't create files as .PHONY
.PHONY: help clean homeassistant-frigate nas \
        requirements rsnapshot upgrade \
        webservers workstation

help:
	@echo "Available targets:"
	@echo "  help                 - Show this help message"
	@echo "  clean               - Remove temporary role files"
	@echo "  requirements        - Install required Ansible roles and collections"
	@echo ""
	@echo "Playbook targets:"
	@echo "  homeassistant-frigate - Configure Home Assistant and Frigate"
	@echo "  nas                 - Configure NAS server"
	@echo "  rsnapshot          - Configure rsnapshot backup"
	@echo "  upgrade            - Run system upgrades"
	@echo "  webservers         - Configure web servers"
	@echo "  workstation        - Configure workstation"

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
