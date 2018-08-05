SHELL := /bin/bash

.DEFAULT_GOAL := workstation
.PHONY: clean requirements rsnapshot upgrade webservers workstation zoneminder

workstation: requirements
	ansible-playbook --ask-become-pass workstation.yml

clean:
	rm -rf .roles

requirements:
	ansible-galaxy install -p .roles/ -r requirements.yml

rsnapshot: requirements
	ansible-playbook --ask-become-pass rsnapshot.yml

upgrade: requirements
	ansible-playbook --ask-become-pass upgrade.yml

webservers: requirements
	ansible-playbook --ask-become-pass webservers.yml

zoneminder: requirements
	ansible-playbook --ask-become-pass zoneminder.yml
