SHELL := /bin/bash

# Arguments after `--` are forwarded verbatim to ansible-playbook, e.g.:
#   make desktop -- --limit tron --tags alacritty
# (make rejects bare --flags, so the `--` separator is required.)
ARGS = $(filter-out $(firstword $(MAKECMDGOALS)),$(MAKECMDGOALS))

# Swallow the forwarded tokens (e.g. --limit, tron) as no-op goals so make
# does not error with "No rule to make target". Real targets have explicit
# rules, which take precedence over this pattern.
%:
	@:

PLAYBOOKS := base desktop dev docker games hobbies homeautomation \
             msmtp nas rsnapshot torrent upgrade webservers

.DEFAULT_GOAL := help

.PHONY: help clean requirements ai_maintainer $(PLAYBOOKS)

help:
	@echo "Available targets:"
	@echo "  clean                 - Remove temporary role files"
	@echo "  help                  - Show this help message"
	@echo "  requirements          - Install required Ansible roles and collections"
	@echo ""
	@echo "Playbook targets:"
	@echo "  base                  - Configure base system"
	@echo "  desktop               - Configure desktop environment"
	@echo "  dev                   - Configure development tools"
	@echo "  docker                - Configure Docker and Kubernetes"
	@echo "  games                 - Configure gaming packages"
	@echo "  hobbies               - Configure hobby tools (3D printing, electronics, FPV)"
	@echo "  homeautomation        - Configure home automation"
	@echo "  msmtp                 - Configure email forwarding"
	@echo "  nas                   - Configure NAS server"
	@echo "  rsnapshot             - Configure rsnapshot backup"
	@echo "  torrent               - Configure rtorrent host and controller scripts"
	@echo "  upgrade               - Run system upgrades"
	@echo "  webservers            - Configure web servers"
	@echo ""
	@echo "Tag targets:"
	@echo "  ai_maintainer         - Configure automated GitHub repository maintenance"
	@echo "                          (dev.yml --tags ai_maintainer; there is no ai_maintainer role)"
	@echo ""
	@echo "Forward extra ansible-playbook arguments after --, e.g.:"
	@echo "  make desktop -- --limit tron --tags alacritty"

clean:
	rm -rf .ansible/roles .ansible/collections

requirements:
	ansible-galaxy role install -r requirements.yml
	ansible-galaxy collection install -r requirements.yml

$(PLAYBOOKS): %: requirements
	ansible-playbook --ask-become-pass $*.yml $(ARGS)

# A tag in the dev role, gated on the ai_maintainer group, rather than a playbook of its own.
ai_maintainer: requirements
	ansible-playbook --ask-become-pass dev.yml --tags ai_maintainer $(ARGS)
