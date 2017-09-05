SHELL := /bin/bash

.DEFAULT_GOAL := workstation
.PHONY: clean requirements rsnapshot upgrade workstation zoneminder

clean:
	rm -rf .roles

requirements:
	ansible-galaxy install -p .roles/ -r requirements.yml

letsencrypt: requirements
	ansible-playbook letsencrypt.yml

rsnapshot: requirements
	ansible-playbook rsnapshot.yml

upgrade: requirements
	ansible-playbook upgrade.yml

websites: requirements
	ansible-playbook websites.yml

workstation: requirements
	ansible-playbook workstation.yml

zoneminder: requirements
	ansible-playbook zoneminder.yml
