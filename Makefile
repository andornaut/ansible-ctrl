SHELL := /bin/bash

.DEFAULT_GOAL := workstation
.PHONY: clean requirements letsencrypt rsnapshot upgrade websites workstation zoneminder

workstation: requirements
	ansible-playbook --ask-become-pass workstation.yml

clean:
	rm -rf .roles

letsencrypt: requirements
	ansible-playbook --ask-become-pass letsencrypt.yml

requirements:
	ansible-galaxy install -p .roles/ -r requirements.yml

rsnapshot: requirements
	ansible-playbook --ask-become-pass rsnapshot.yml

upgrade: requirements
	ansible-playbook --ask-become-pass upgrade.yml

websites: requirements
	ansible-playbook --ask-become-pass websites.yml

zoneminder: requirements
	ansible-playbook --ask-become-pass zoneminder.yml
