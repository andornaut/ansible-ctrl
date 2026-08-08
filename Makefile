SHELL := /bin/bash

# Arguments after `--` are forwarded verbatim to ansible-playbook, e.g.:
#   make desktop -- --limit example --tags alacritty
# (make rejects bare --flags, so the `--` separator is required.)
ARGS = $(filter-out $(firstword $(MAKECMDGOALS)),$(MAKECMDGOALS))

# Swallow the forwarded tokens (e.g. --limit, example) as no-op goals so make
# does not error with "No rule to make target". Real targets have explicit
# rules, which take precedence over this pattern.
%:
	@:

PLAYBOOKS := base desktop dev docker faramir faramir_fleet \
             games hobbies homeautomation msmtp nas rsnapshot torrent upgrade \
             webservers

.DEFAULT_GOAL := help

.PHONY: help clean requirements $(PLAYBOOKS)

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
	@echo "  faramir               - Install the faramir secret broker on the controller"
	@echo "  faramir_fleet         - Authorize the broker's SSH key on the managed hosts"
	@echo "                          (needs ASK_PASS=1 until those hosts have NOPASSWD sudo)"
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
	@echo "Forward extra ansible-playbook arguments after --, e.g.:"
	@echo "  make desktop -- --limit example --tags alacritty"

clean:
	rm -rf .ansible/roles .ansible/collections .ansible/.requirements

# A stamp rather than a phony recipe: a wrapped target runs make twice, and a
# phony prerequisite would install the galaxy content on both passes. `make
# clean` removes it along with what it stands for.
requirements: .ansible/.requirements

.ansible/.requirements: requirements.yml
	@mkdir -p $(@D)
	ansible-galaxy role install -r requirements.yml
	ansible-galaxy collection install -r requirements.yml
	@touch $@


# Not $(MAKE): make runs any recipe line containing that string even under -n,
# which makes a dry run wet.
SUBMAKE := $(MAKE)

# Root needs neither a become password nor the operator's age identity, and both
# decisions below read this.
IS_ROOT := $(filter 0,$(shell id -u))

# The store lives in the operator's home, so it has to be resolved rather than
# named: a root run has HOME=/root, and SUDO_USER is the account that invoked it.
# getent rather than ~, which expands to the wrong home for exactly that run.
OPERATOR := $(if $(SUDO_USER),$(SUDO_USER),$(shell id -un))
OPERATOR_HOME := $(shell getent passwd $(OPERATOR) | cut -d: -f6)
SOPS_FILE := $(OPERATOR_HOME)/.faramir/secrets/ansible-ctrl.sops.yml

# sops looks for an identity under $HOME, which is /root for a root run, so it
# would find none. The keeper's key is already a recipient and root can read it
# whatever its mode. ?= leaves an operator-set value alone.
ifdef IS_ROOT
export SOPS_AGE_KEY_FILE ?= /etc/faramir/age.key
endif

# Re-enter under sops exec-env when the values are not in the environment yet.
# SECRETS_LOADED marks the inner half; SECRETS=none skips it for a playbook that
# needs no credential. An absent SOPS_FILE makes it a no-op.
WRAP = $(if $(or $(SECRETS_LOADED),$(filter none,$(SECRETS))),,$(wildcard $(SOPS_FILE)))

# Prompt for a become password only when the run reaches the controller, the one
# host whose sudo asks for one. Asked of ansible rather than assumed, so a
# --limit in ARGS counts. One startup, connecting to nothing, roughly 0.4s.
#
# Two ways a run reaches it: the controller is in the play's host list, or a role
# runs a become task under delegate_to: localhost, which no host list shows.
list_run = ansible-playbook $(1).yml $(ARGS) --list-hosts --list-tasks 2>/dev/null

# Host names sit under "hosts (N):" and stop where the task list starts.
pick_hosts = awk '/hosts \([0-9]+\):/{f=1;next} /^[[:space:]]*tasks:/{f=0} /^[[:space:]]*$$/{f=0} f{gsub(/^[[:space:]]+|[[:space:]]+$$/,"");print}'

# Task lines read "  <role> : <name>", so the role is everything before " : ".
pick_roles = awk '/^[[:space:]]+[^ ]+ : /{sub(/ :.*/,"");gsub(/^[[:space:]]+/,"");print}' | sort -u

# IS_ROOT is tested first: sudo asks root for nothing, and ansible prompts at
# startup whether or not the password is used. Then ASK_PASS=1, which forces the
# prompt for the fleet play, the run that establishes the NOPASSWD the rest rely
# on.
define become_flag
$(if $(IS_ROOT),,$(if $(ASK_PASS),--ask-become-pass,$$( \
  run=$$($(call list_run,$(1))); \
  controller=$$(ansible faramir --list-hosts 2>/dev/null | $(pick_hosts)); \
  for h in $$(echo "$$run" | $(pick_hosts)); do \
    for c in $$controller; do [ "$$h" = "$$c" ] && { echo --ask-become-pass; exit 0; }; done; \
  done; \
  for r in $$(echo "$$run" | $(pick_roles)); do \
    grep -rqsE 'delegate_to:[[:space:]]*localhost' roles/$$r && { echo --ask-become-pass; exit 0; }; \
  done)))
endef

# The `--` is repeated on the re-entry for the same reason it is required on the
# way in: the inner make parses ARGS as its own options and rejects the first
# --flag among them. Without it, forwarding works only while SOPS_FILE is absent.
$(PLAYBOOKS): %: requirements
	@if [ -n "$(WRAP)" ]; then \
	   sops exec-env $(SOPS_FILE) 'SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory $* -- $(ARGS)'; \
	 else \
	   ansible-playbook $(call become_flag,$*) $*.yml $(ARGS); \
	 fi
