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

# sops looks for an identity under $HOME, which is /root for a root run, so it
# would find none. The keeper's key is already a recipient and root can read it
# whatever its mode. It sits beside the store, so it is resolved from the
# operator's home the same way. ?= leaves an operator-set value alone.
ifdef IS_ROOT
export SOPS_AGE_KEY_FILE ?= $(OPERATOR_HOME)/.faramir/age.key
endif

# The runs that read a secret_* variable. Only these re-enter under sops; the
# rest reach no credential and must not be stopped for want of one.
#
#   homeautomation  the role's own defaults and tasks
#   msmtp           msmtp_password, set for every host
#   webservers      cloudflare_api_token and basicauth_password
#
# A list rather than something derived from the run. A credential reaches a play
# through host_vars, which ansible templates lazily, so `msmtp_password` is set
# on every host here and costs nothing until the msmtp role reads it. Grepping
# host_vars therefore answers yes for every run, and grepping the roles in the
# run answers no for msmtp and webservers, whose roles name a plain variable
# that host_vars happens to bind to a secret. Telling the two apart means
# resolving which variables each role reads, which is not a thing make can do.
#
# So: giving a playbook its first credential means adding it here.
SECRET_PLAYBOOKS := homeautomation msmtp webservers

# Re-enter under sops exec-env when the values are not in the environment yet.
# SECRETS_LOADED marks the inner half; SECRETS=none skips it for a run that
# turns out to need no credential, a --tags run being the usual reason.
LOAD_SECRETS = $(if $(or $(SECRETS_LOADED),$(filter none,$(SECRETS))),,$(filter $*,$(SECRET_PLAYBOOKS)))

# SECRETS=none has to reach the play as well as the re-entry above. A
# secret-bearing playbook asserts in pre_tasks that credentials were injected,
# and this is the operator saying this run reads none, so the assert is the one
# thing that must not outlive the decision to skip the injection.
SECRETS_FLAG = $(if $(filter none,$(SECRETS)),--extra-vars secrets_required=false)

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

# A secret-bearing run whose store cannot be read is stopped rather than
# attempted. Every secret_* variable would be undefined, and the first task to
# read one fails with the tasks before it already applied, which for a container
# means it is removed and not recreated. Absent and unreadable are not told
# apart, because for these playbooks either one ends the same way.
#
# The store belongs to a group the operator is not in, so the two accounts that
# can serve such a run are root and the broker's executor, and neither covers the
# whole fleet: root reads the store but has no key for any host it must reach
# over ssh, and the executor authenticates everywhere but has no sudo on the
# controller, deliberately. So the message names both and leaves the --limit to
# the operator rather than guessing at one.
#
# The `--` is repeated on the re-entry for the same reason it is required on the
# way in: the inner make parses ARGS as its own options and rejects the first
# --flag among them.
$(PLAYBOOKS): %: requirements
	@if [ -n "$(LOAD_SECRETS)" ] && [ ! -r "$(SOPS_FILE)" ]; then \
	   controller=$$(ansible faramir --list-hosts 2>/dev/null | $(pick_hosts) | head -1); \
	   echo "$(SOPS_FILE): not readable by $(OPERATOR)" >&2; \
	   echo "Refusing to run $*.yml: every secret_* variable would be undefined," >&2; \
	   echo "and the first task to read one fails with the tasks before it already" >&2; \
	   echo "applied. Run it as root, which reads the store:" >&2; \
	   echo "  sudo make $* -- --limit $$controller$(if $(ARGS), $(ARGS))" >&2; \
	   echo "or through the broker, for every host but the controller:" >&2; \
	   echo "  faramir run --env-file faramir.env -- \\" >&2; \
	   echo "      ansible-playbook $*.yml --limit '!faramir'$(if $(ARGS), $(ARGS))" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(LOAD_SECRETS)" ]; then \
	   sops exec-env $(SOPS_FILE) 'SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory $* -- $(ARGS)'; \
	 else \
	   ansible-playbook $(call become_flag,$*) $(SECRETS_FLAG) $*.yml $(ARGS); \
	 fi
