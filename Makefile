SHELL := /bin/bash

.DEFAULT_GOAL := help

.PHONY: help clean requirements \
        base bspwm desktop dev docker games msmtp niri \
        homeassistant-frigate nas rsnapshot upgrade webservers

help:
	@echo "Available targets:"
	@echo "  help                  - Show this help message"
	@echo "  clean                 - Remove temporary role files"
	@echo "  requirements          - Install required Ansible roles and collections"
	@echo ""
	@echo "Playbook targets:"
	@echo "  base                  - Configure base system"
	@echo "  bspwm                 - Configure BSPWM window manager"
	@echo "  desktop               - Configure desktop environment"
	@echo "  dev                   - Configure development tools"
	@echo "  docker                - Configure Docker and Kubernetes"
	@echo "  games                 - Configure gaming packages"
	@echo "  homeassistant-frigate - Configure Home Assistant and Frigate"
	@echo "  msmtp                 - Configure email forwarding"
	@echo "  nas                   - Configure NAS server"
	@echo "  niri                  - Configure Niri compositor"
	@echo "  rsnapshot             - Configure rsnapshot backup"
	@echo "  upgrade               - Run system upgrades"
	@echo "  webservers            - Configure web servers"

clean:
	rm -rf .roles

requirements:
	ansible-galaxy role install -r requirements.yml
	ansible-galaxy collection install -r requirements.yml

base: requirements
	ansible-playbook --ask-become-pass base.yml

bspwm: requirements
	ansible-playbook --ask-become-pass bspwm.yml

desktop: requirements
	ansible-playbook --ask-become-pass desktop.yml

dev: requirements
	ansible-playbook --ask-become-pass dev.yml

docker: requirements
	ansible-playbook --ask-become-pass docker.yml

games: requirements
	ansible-playbook --ask-become-pass games.yml

homeassistant-frigate: requirements
	ansible-playbook --ask-become-pass homeassistant-frigate.yml

msmtp: requirements
	ansible-playbook --ask-become-pass msmtp.yml

nas: requirements
	ansible-playbook --ask-become-pass nas.yml

niri: requirements
	ansible-playbook --ask-become-pass niri.yml

rsnapshot: requirements
	ansible-playbook --ask-become-pass rsnapshot.yml

upgrade: requirements
	ansible-playbook --ask-become-pass upgrade.yml

webservers: requirements
	ansible-playbook --ask-become-pass webservers.yml
