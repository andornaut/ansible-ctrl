SHELL := /bin/bash

# Arguments after `--` are forwarded verbatim to ansible-playbook; the separator is
# required, make rejecting bare --flags. See README.
#
# Every goal but the first, rather than every goal that is not the target: `make desktop
# -- --limit desktop` would otherwise drop the token from its own argument list.
GOAL_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
ARGS = $(GOAL_ARGS)

# An argument containing = never reaches ansible-playbook, make taking it as a variable
# assignment before the goal list is built. ARGS='...' is the route for one, and a
# command-line ARGS outranks the goal-derived list, whose leftovers the %: rule below
# swallows. bin/playbook.py refuses the run in both cases, and knows which assignments are
# its own knobs.
ifeq ($(origin ARGS),command line)
ASSIGNMENTS :=
DROPPED_ARGS := $(GOAL_ARGS)
else
ASSIGNMENTS := $(MAKEOVERRIDES)
DROPPED_ARGS :=
endif

# Swallow the forwarded tokens as no-op goals, or make errors with "No rule to make
# target". Real targets have explicit rules, which outrank this pattern.
%:
	@:

PLAYBOOKS := base desktop dev docker faramir \
             games hobbies homeautomation msmtp nas router rsnapshot torrent upgrade \
             webservers

PLAYBOOK := bin/playbook.py

.DEFAULT_GOAL := help

.PHONY: help clean lint requirements bootstrap $(PLAYBOOKS)

IS_ROOT := $(filter 0,$(shell id -u))

# Recipes write into the work tree as the operator, so a root run leaves nothing an
# unprivileged `make` cannot rebuild. A tree checked out by root resolves to root and
# nothing drops.
OPERATOR := $(shell $(PLAYBOOK) operator)
AS_OPERATOR := $(if $(IS_ROOT),runuser -u $(OPERATOR) --)

help:
	@echo "Available targets:"
	@echo "  bootstrap             - Apply base, docker, then every playbook with a group"
	@echo "                          holding the host: make bootstrap -- --limit <host>"
	@echo "  clean                 - Remove downloaded collections and lint tooling"
	@echo "  help                  - Show this help message"
	@echo "  lint                  - Run every check CI gates on"
	@echo "  requirements          - Install required Ansible collections"
	@echo ""
	@echo "Playbook targets:"
	@echo "  base                  - Configure base system"
	@echo "  desktop               - Configure desktop environment"
	@echo "  dev                   - Configure development tools"
	@echo "  docker                - Configure Docker and Kubernetes"
	@echo "  faramir               - Install the faramir secret broker on every faramir host,"
	@echo "                          then authorize the controller's SSH key on the managed hosts"
	@echo "  games                 - Configure gaming packages"
	@echo "  hobbies               - Configure hobby tools (3D printing, electronics, FPV)"
	@echo "  homeautomation        - Configure home automation"
	@echo "  msmtp                 - Configure email forwarding"
	@echo "  nas                   - Configure NAS server"
	@echo "  router                - Configure the pfSense router health checks"
	@echo "  rsnapshot             - Configure rsnapshot backup"
	@echo "  torrent               - Configure rtorrent host and controller scripts"
	@echo "  upgrade               - Run system upgrades"
	@echo "  webservers            - Configure web servers"
	@echo ""
	@echo "Forward extra ansible-playbook arguments after --, e.g.:"
	@echo "  make desktop -- --limit example --tags alacritty"
	@echo ""
	@echo "An argument containing = has to be passed as ARGS instead, e.g.:"
	@echo "  make desktop ARGS='--extra-vars foo=bar'"
	@echo ""
	@echo "Variables:"
	@echo "  SECRETS=none          - Skip the sops re-entry, for a run that reads no credential"
	@echo "  ASK_PASS=1            - Force --ask-become-pass"
	@echo "  PREFLIGHT=none        - Skip the reachability check, and attempt every host regardless"

clean:
	rm -rf .ansible/collections .ansible/.requirements .ansible/lint-venv node_modules

# The same checks CI runs, from the same script. Depends on requirements:
# ansible-lint's syntax-check reports every collection module unknown without them.
lint: requirements
	@$(AS_OPERATOR) tests/lint.sh

# A stamp, not a phony recipe, so a run that goes through make more than once installs the
# galaxy content once.
requirements: .ansible/.requirements

# Everything under .ansible/ belongs to the operator: runuser cannot write into a
# root-owned tree, and tests/lint.sh builds its venv in the same directory.
.ansible/.requirements: requirements.yml
	@$(AS_OPERATOR) mkdir -p $(@D)
	@$(if $(IS_ROOT),chown -R $(OPERATOR) $(@D))
	$(AS_OPERATOR) ansible-galaxy collection install -r requirements.yml
	@$(AS_OPERATOR) touch $@

# Exported rather than quoted onto the command line, being whatever was typed.
$(PLAYBOOKS) bootstrap: export PLAYBOOK_ASSIGNMENTS := $(ASSIGNMENTS)
$(PLAYBOOKS) bootstrap: export PLAYBOOK_DROPPED_ARGS := $(DROPPED_ARGS)

# Only the first goal is applied: every inventory group is also a playbook here, so
# `make base -- --limit desktop` would otherwise apply desktop as well. A command-line
# SECRETS, ASK_PASS or PREFLIGHT reaches the script through the environment, where make
# exports every command-line assignment.
$(PLAYBOOKS): %: requirements
	@$(if $(filter $*,$(firstword $(MAKECMDGOALS))),$(PLAYBOOK) run $* $(ARGS),:)

bootstrap: requirements
	@$(if $(filter $@,$(firstword $(MAKECMDGOALS))),$(PLAYBOOK) bootstrap $(ARGS),:)
