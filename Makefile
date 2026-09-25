SHELL := /bin/bash

# Arguments after `--` are forwarded to ansible-playbook word by word, so one containing
# whitespace arrives split; the separator is required, make rejecting bare --flags. See
# README.
#
# Every goal but the first, rather than every goal that is not the target: `make desktop
# -- --limit desktop` would otherwise drop the token from its own argument list.
GOAL_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
# Each word single-quoted for the recipe's shell, so a host pattern such as `all:&dev` or
# `web*` reaches ansible-playbook as typed instead of being run or globbed.
ARGS = $(foreach word,$(GOAL_ARGS),'$(subst ','\'',$(word))')

# An argument containing = never reaches ansible-playbook, make taking it as a variable
# assignment before the goal list is built. ARGS='...' is the route for one, and a
# command-line ARGS outranks the goal-derived list, whose leftovers the %: rule below
# swallows. bin/playbook.py refuses the run in both cases, and knows which assignments are
# its own knobs.
#
# MAKEOVERRIDES escapes a space inside a value as "\ ", so ARGS is one word to filter out
# only while those are held aside.
SPACE_MARK := <space>
ifeq ($(origin ARGS),command line)
ASSIGNMENTS := $(subst $(SPACE_MARK),\ ,$(filter-out ARGS=%,$(subst \ ,$(SPACE_MARK),$(MAKEOVERRIDES))))
DROPPED_ARGS := $(GOAL_ARGS)
else
ASSIGNMENTS := $(MAKEOVERRIDES)
DROPPED_ARGS :=
endif

# Swallow the forwarded tokens as no-op goals, or make errors with "No rule to make
# target". Real targets have explicit rules, which outrank this pattern. A first goal
# landing here is a mistyped target, and fails.
%:
	@$(if $(filter $@,$(FIRST_GOAL)),echo "make: no target '$@' (see make help)" >&2; exit 2,:)

PLAYBOOKS := base desktop dev docker faramir \
             games hobbies homeautomation msmtp nas router rsnapshot torrent upgrade \
             webservers

PLAYBOOK := bin/playbook.py

.DEFAULT_GOAL := help

# The goal this invocation applies. Every other goal is a forwarded word, and one that
# names a target (`--tags clean`) must not run it.
FIRST_GOAL = $(or $(firstword $(MAKECMDGOALS)),$(.DEFAULT_GOAL))
HELP_ECHO = $(if $(filter help,$(FIRST_GOAL)),echo,:)

.PHONY: help clean lint requirements $(PLAYBOOKS)

IS_ROOT := $(filter 0,$(shell id -u))

# Recipes write into the work tree as the operator, so a root run leaves nothing an
# unprivileged `make` cannot rebuild. A tree checked out by root resolves to root and
# nothing drops.
OPERATOR := $(shell $(PLAYBOOK) operator)
AS_OPERATOR := $(if $(IS_ROOT),runuser -u $(OPERATOR) --)

help:
	@$(HELP_ECHO) "Available targets:"
	@$(HELP_ECHO) "  clean                 - Remove downloaded collections, lint tooling and the git hooks"
	@$(HELP_ECHO) "  help                  - Show this help message"
	@$(HELP_ECHO) "  lint                  - Run every check CI gates on"
	@$(HELP_ECHO) "  requirements          - Install required Ansible collections"
	@$(HELP_ECHO) ""
	@$(HELP_ECHO) "Playbook targets:"
	@$(HELP_ECHO) "  base                  - Configure base system"
	@$(HELP_ECHO) "  desktop               - Configure desktop environment"
	@$(HELP_ECHO) "  dev                   - Configure development tools"
	@$(HELP_ECHO) "  docker                - Configure Docker and Kubernetes"
	@$(HELP_ECHO) "  faramir               - Install the faramir secret broker on every faramir host,"
	@$(HELP_ECHO) "                          then authorize the controller's SSH key on the managed hosts"
	@$(HELP_ECHO) "  games                 - Configure gaming packages"
	@$(HELP_ECHO) "  hobbies               - Configure hobby tools (3D printing, electronics, FPV)"
	@$(HELP_ECHO) "  homeautomation        - Configure home automation"
	@$(HELP_ECHO) "  msmtp                 - Configure email forwarding"
	@$(HELP_ECHO) "  nas                   - Configure NAS server"
	@$(HELP_ECHO) "  router                - Configure the pfSense router health checks"
	@$(HELP_ECHO) "  rsnapshot             - Configure rsnapshot backup"
	@$(HELP_ECHO) "  torrent               - Configure rtorrent host and controller scripts"
	@$(HELP_ECHO) "  upgrade               - Run system upgrades"
	@$(HELP_ECHO) "  webservers            - Configure web servers"
	@$(HELP_ECHO) ""
	@$(HELP_ECHO) "Forward extra ansible-playbook arguments after --, e.g.:"
	@$(HELP_ECHO) "  make desktop -- --limit example --tags alacritty"
	@$(HELP_ECHO) ""
	@$(HELP_ECHO) "An argument containing = or whitespace has to be passed as ARGS instead, e.g.:"
	@$(HELP_ECHO) "  make desktop ARGS='--extra-vars foo=bar'"
	@$(HELP_ECHO) ""
	@$(HELP_ECHO) "Variables:"
	@$(HELP_ECHO) "  SECRETS=none          - Skip sops, for a run that reads no credential"
	@$(HELP_ECHO) "  ASK_PASS=1            - Force --ask-become-pass"
	@$(HELP_ECHO) "  PREFLIGHT=none        - Skip the reachability check, and attempt every host regardless"

# node_modules holds the lint-staged the pre-commit hook runs, so the hooks path husky's
# `prepare` set goes with it: npx would otherwise fetch an unpinned lint-staged at the next
# commit. `make lint` runs `npm ci`, whose `prepare` sets it again.
clean:
	$(if $(filter $@,$(FIRST_GOAL)),rm -rf .ansible/collections .ansible/.requirements .ansible/lint-venv node_modules,@:)
	$(if $(filter $@,$(FIRST_GOAL)),[ "$$(git config --local --get core.hooksPath)" != .husky/_ ] || git config --local --unset core.hooksPath,@:)

# The same checks CI runs, from the same script. Depends on requirements:
# ansible-lint's syntax-check reports every collection module unknown without them.
lint: requirements
	@$(if $(filter $@,$(FIRST_GOAL)),$(AS_OPERATOR) tests/lint.sh,:)

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
$(PLAYBOOKS): export PLAYBOOK_ASSIGNMENTS := $(ASSIGNMENTS)
$(PLAYBOOKS): export PLAYBOOK_DROPPED_ARGS := $(DROPPED_ARGS)

# Only the first goal is applied: every inventory group is also a playbook here, so
# `make base -- --limit desktop` would otherwise apply desktop as well. A command-line
# SECRETS, ASK_PASS or PREFLIGHT reaches the script through the environment, where make
# exports every command-line assignment.
$(PLAYBOOKS): %: requirements
	@$(if $(filter $*,$(FIRST_GOAL)),$(PLAYBOOK) run $* $(ARGS),:)
