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

.PHONY: help clean lint requirements $(PLAYBOOKS)

help:
	@echo "Available targets:"
	@echo "  clean                 - Remove temporary role files"
	@echo "  help                  - Show this help message"
	@echo "  lint                  - Run every check CI gates on"
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
	rm -rf .ansible/roles .ansible/collections .ansible/.requirements .ansible/lint-venv

# The same four checks CI runs, from the same script, so passing here is passing
# there. Depends on requirements: ansible-lint's syntax-check resolves the
# collections' modules, and reports every one of them as unknown without them.
lint: requirements
	@tests/lint.sh

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
SECRETS_DIR := $(dir $(SOPS_FILE))

# sops looks for an identity under $HOME, which is /root for a root run, so it
# would find none. The keeper's key is already a recipient and root can read it
# whatever its mode. It sits beside the store, so it is resolved from the
# operator's home the same way. ?= leaves an operator-set value alone.
ifdef IS_ROOT
export SOPS_AGE_KEY_FILE ?= $(OPERATOR_HOME)/.faramir/age.key
endif

# Re-enter under sops exec-env when the values are not in the environment yet.
# SECRETS_LOADED marks the inner half; SECRETS=none skips it for a playbook that
# needs no credential. An absent SOPS_FILE still makes it a no-op, but the
# recipe decides that, not $(wildcard): see the assertion below.
LOAD_SECRETS = $(if $(or $(SECRETS_LOADED),$(filter none,$(SECRETS))),,1)

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

# A store that cannot be read is an error; only one that is genuinely absent is a
# no-op. The two are indistinguishable to $(wildcard), which reports nothing for
# both, and running anyway leaves every secret_* variable undefined: the first
# task to use one fails after the tasks before it have applied, which for a
# container means it is removed and not recreated.
#
# The file is unreadable when it exists but cannot be opened, and also when the
# directory holding it cannot be searched, since then whether it exists cannot be
# established either. SECRETS_DIR is stat-able whatever its mode, its own parent
# being the operator's home.
#
# The `--` is repeated on the re-entry for the same reason it is required on the
# way in: the inner make parses ARGS as its own options and rejects the first
# --flag among them. Without it, forwarding works only while SOPS_FILE is absent.
$(PLAYBOOKS): %: requirements
	@if [ -n "$(LOAD_SECRETS)" ] && [ ! -r "$(SOPS_FILE)" ] \
	    && { [ -e "$(SOPS_FILE)" ] \
	         || { [ -d "$(SECRETS_DIR)" ] && [ ! -x "$(SECRETS_DIR)" ]; }; }; then \
	   echo "$(SOPS_FILE): not readable by $(OPERATOR)" >&2; \
	   echo "Refusing to run: every secret_* variable would be undefined, and the" >&2; \
	   echo "first task to use one fails with the tasks before it already applied." >&2; \
	   echo "Run it as root, or through the broker:" >&2; \
	   echo "  faramir run --env-file faramir.env -- ansible-playbook $*.yml $(ARGS)" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(LOAD_SECRETS)" ] && [ -r "$(SOPS_FILE)" ]; then \
	   sops exec-env $(SOPS_FILE) 'SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory $* -- $(ARGS)'; \
	 else \
	   ansible-playbook $(call become_flag,$*) $*.yml $(ARGS); \
	 fi
