SHELL := /bin/bash

.DEFAULT_GOAL := workstation
.PHONY: clean requirements rsnapshot upgrade websites workstation zoneminder

clean:
	rm -rf .roles

requirements:
	ansible-galaxy install -p .roles/ -r requirements.yml

letsencrypt: requirements
	ansible-playbook --ask-become-pass letsencrypt.yml

rsnapshot: requirements
	ansible-playbook --ask-become-pass rsnapshot.yml

upgrade: requirements
	ansible-playbook --ask-become-pass upgrade.yml

websites: requirements
	ansible-playbook --ask-become-pass websites.yml

workstation: requirements
	ansible-playbook --ask-become-pass workstation.yml

zoneminder: requirements
	ansible-playbook --ask-become-pass zoneminder.yml
