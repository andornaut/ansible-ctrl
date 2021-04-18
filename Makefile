SHELL := /bin/bash

.DEFAULT_GOAL := workstation
.PHONY: clean homeassistant requirements rsnapshot upgrade webservers workstation zoneminder

clean:
	rm -rf .roles

homeassistant: requirements
	ansible-playbook --ask-become-pass homeassistant.yml

requirements:
	ansible-galaxy install -p .roles/ -r requirements.yml

rsnapshot: requirements
	ansible-playbook --ask-become-pass rsnapshot.yml

upgrade: requirements
	ansible-playbook --ask-become-pass upgrade.yml

webservers: requirements
	ansible-playbook --ask-become-pass webservers.yml

workstation: requirements
	ansible-playbook --ask-become-pass workstation.yml

zoneminder: requirements
	ansible-playbook --ask-become-pass zoneminder.yml
