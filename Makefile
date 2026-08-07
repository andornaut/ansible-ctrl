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

PLAYBOOKS := base desktop dev docker faramir faramir_fleet games hobbies \
             homeautomation msmtp nas rsnapshot torrent upgrade webservers

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


# Where the credentials come from, and whether a password has to be typed.
#
# Both are decided per invocation rather than always-on, because both used to be
# unconditional and both were usually wrong: every run asked for a sudo password
# it would not use, and every run needing a credential had to be wrapped by hand.
#
# SOPS_FILE absent means the vault has not been migrated yet, and everything
# below is a no-op: the run behaves exactly as it always did.
# Not $(MAKE): make runs any recipe line containing that string even under -n,
# which makes a dry run wet. Referenced through another name, -n stays dry.
SUBMAKE := $(MAKE)

SOPS_FILE := group_vars/all/vault.sops.yml

# Re-enter under sops exec-env when the values are not in the environment yet.
# SECRETS_LOADED marks the inner half so this happens once; SECRETS=none skips
# it for a playbook that needs no credential.
WRAP = $(if $(or $(SECRETS_LOADED),$(filter none,$(SECRETS))),,$(wildcard $(SOPS_FILE)))

# Prompt for a become password only when the run actually reaches a host whose
# sudo asks for one, which is the controller: the fleet is NOPASSWD, and a
# brokered run cannot become there at all.  Asked of ansible rather than
# assumed, so a --limit in ARGS is accounted for.  Roughly 0.4s.
#
#   make homeautomation                    -> reaches tron, prompts
#   make homeautomation -- --limit snorlax -> does not, so it does not
# Whether a run needs a sudo password, decided per invocation rather than always
# asked for. Two ways a run reaches the controller, and both have to be checked:
#
#   it targets it        tron is in the play's host list
#   it delegates to it   a role runs a become task with delegate_to: localhost,
#                        which no host list ever shows (make torrent targets
#                        prime and still writes /usr/local/bin on the controller)
#
# --list-hosts and --list-tasks combine into one call and connect to nothing, so
# this costs one ansible startup. The delegation check greps the roles that call
# actually named, so a role that gains a delegation is covered without anyone
# remembering to update a list here.
#
# It errs toward asking: a delegate_to naming a remote host would prompt for
# nothing, which costs a keystroke. Not asking costs a half-applied run.
list_run = ansible-playbook $(1).yml $(ARGS) --list-hosts --list-tasks 2>/dev/null

# Host names sit under "hosts (N):" and stop where the task list starts.
pick_hosts = awk '/hosts \([0-9]+\):/{f=1;next} /^[[:space:]]*tasks:/{f=0} /^[[:space:]]*$$/{f=0} f{gsub(/^[[:space:]]+|[[:space:]]+$$/,"");print}'

# Task lines read "  <role> : <name>", so the role is everything before " : ".
pick_roles = awk '/^[[:space:]]+[^ ]+ : /{sub(/ :.*/,"");gsub(/^[[:space:]]+/,"");print}' | sort -u

# ASK_PASS=1 forces it. The fleet play is the run that establishes the NOPASSWD
# making prompts unnecessary, so it is the one run that still needs one.
define become_flag
$(if $(ASK_PASS),--ask-become-pass,$$( \
  run=$$($(call list_run,$(1))); \
  controller=$$(ansible faramir --list-hosts 2>/dev/null | $(pick_hosts)); \
  for h in $$(echo "$$run" | $(pick_hosts)); do \
    for c in $$controller; do [ "$$h" = "$$c" ] && { echo --ask-become-pass; exit 0; }; done; \
  done; \
  for r in $$(echo "$$run" | $(pick_roles)); do \
    grep -rqsE 'delegate_to:[[:space:]]*localhost' roles/$$r && { echo --ask-become-pass; exit 0; }; \
  done))
endef

$(PLAYBOOKS): %: requirements
	@if [ -n "$(WRAP)" ]; then \
	   sops exec-env $(SOPS_FILE) 'SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory $* $(ARGS)'; \
	 else \
	   ansible-playbook $(call become_flag,$*) $*.yml $(ARGS); \
	 fi

# A tag in the dev role, gated on the ai_maintainer group, rather than a playbook of its own.
ai_maintainer: requirements
	@if [ -n "$(WRAP)" ]; then \
	   sops exec-env $(SOPS_FILE) 'SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory ai_maintainer $(ARGS)'; \
	 else \
	   ansible-playbook $(call become_flag,dev) dev.yml --tags ai_maintainer $(ARGS); \
	 fi
