SHELL := /bin/bash

.DEFAULT_GOAL := workstation
.PHONY: clean requirements rsnapshot upgrade workstation zoneminder

clean:
	rm -rf .roles

requirements:
	ansible-galaxy install -p .roles/ -r requirements.yml

rsnapshot: requirements
	ansible-playbook rsnapshot.yml

upgrade: requirements
	ansible-playbook upgrade.yml

workstation: requirements
	ansible-playbook workstation.yml

zoneminder: requirements
	ansible-playbook zoneminder.yml
