SHELL := /bin/bash

# Arguments after `--` are forwarded verbatim to ansible-playbook; the separator is
# required, make rejecting bare --flags. See README.
ARGS = $(filter-out $(firstword $(MAKECMDGOALS)),$(MAKECMDGOALS))

# An argument containing = does not survive that route: make takes it as a variable
# assignment before the goal list is built, and the flag forwards with nothing after it.
# What make took lands here and the run is refused rather than run short. ARGS='...'
# sends one and suppresses the check.
ifeq ($(origin ARGS),command line)
STRAY_ARGS :=
else
STRAY_ARGS := $(filter-out SECRETS=% ASK_PASS=%,$(MAKEOVERRIDES))
endif

# Swallow the forwarded tokens as no-op goals, or make errors with "No rule to make
# target". Real targets have explicit rules, which outrank this pattern.
%:
	@:

PLAYBOOKS := base desktop dev docker faramir \
             games hobbies homeautomation msmtp nas rsnapshot torrent upgrade \
             webservers

.DEFAULT_GOAL := help

.PHONY: help clean lint requirements $(PLAYBOOKS)

# Root needs neither a become password nor the operator's age identity.
IS_ROOT := $(filter 0,$(shell id -u))

# The galaxy content and the store both sit under an account, so the home is resolved
# rather than named: a root run has HOME=/root and SUDO_USER names who invoked it. Read
# only for a root run, a stale SUDO_USER being what any other would find. getent rather
# than ~, which expands wrong for exactly the run that needs this.
OPERATOR := $(or $(and $(IS_ROOT),$(SUDO_USER)),$(shell id -un))
OPERATOR_HOME := $(shell getent passwd $(OPERATOR) | cut -d: -f6)

# Recipes write into the work tree as the operator, so a root run leaves nothing an
# unprivileged `make` cannot rebuild. runuser rather than sudo, this already being root.
# A real root login has no SUDO_USER, so OPERATOR is root and nothing drops.
AS_OPERATOR := $(if $(IS_ROOT),runuser -u $(OPERATOR) --)

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
	@echo "  faramir               - Install the faramir secret broker on the controller,"
	@echo "                          then authorize its SSH key on the managed hosts"
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
	@echo ""
	@echo "An argument containing = has to be passed as ARGS instead, e.g.:"
	@echo "  make desktop ARGS='--extra-vars foo=bar'"
	@echo ""
	@echo "Variables:"
	@echo "  SECRETS=none          - Skip the sops re-entry, for a run that reads no credential"
	@echo "  ASK_PASS=1            - Force --ask-become-pass"

clean:
	rm -rf .ansible/roles .ansible/collections .ansible/.requirements .ansible/lint-venv

# The same four checks CI runs, from the same script. Depends on requirements:
# ansible-lint's syntax-check reports every collection module unknown without them.
lint: requirements
	@$(AS_OPERATOR) tests/lint.sh

# A stamp, not a phony recipe: a wrapped target runs make twice, and a phony
# prerequisite would install the galaxy content on both passes.
requirements: .ansible/.requirements

# Everything under .ansible/ belongs to the operator: runuser cannot write into a
# root-owned tree, and tests/lint.sh builds its venv in the same directory.
.ansible/.requirements: requirements.yml
	@$(AS_OPERATOR) mkdir -p $(@D)
	@$(if $(IS_ROOT),chown -R $(OPERATOR) $(@D))
	$(AS_OPERATOR) ansible-galaxy role install -r requirements.yml
	$(AS_OPERATOR) ansible-galaxy collection install -r requirements.yml
	@$(AS_OPERATOR) touch $@

# Not $(MAKE): make runs any recipe line containing that string even under -n.
SUBMAKE := $(MAKE)

# In the operator's home, resolved above.
SOPS_FILE := $(OPERATOR_HOME)/.config/faramir/secrets/ansible-ctrl.sops.yml

# sops looks for an identity under $HOME, and root's is /root, so the key is named. The
# keeper's key is already a recipient and root reads it whatever its mode. ?= leaves an
# operator-set value alone; the letsencrypt_nginx renewal cron names it for the same
# reason, being the other root-run entry point.
#
# ssh is not redirected: root's own ~/.ssh reaches the fleet, and the operator's config
# would supply aliases without an identity, every ~ in it expanding to /root.
ifdef IS_ROOT
export SOPS_AGE_KEY_FILE ?= $(OPERATOR_HOME)/.config/faramir/age.key
endif

# The runs that read a secret_* variable, and so the only ones that re-enter under sops.
# Giving a playbook its first credential means adding it here.
#
# A list rather than something derived: grepping host_vars answers yes for every run
# (msmtp_password is bound on every host and templated lazily), grepping the roles answers
# no for msmtp and webservers (whose roles name a plain variable host_vars binds to a
# secret). Telling them apart needs variable resolution, which make cannot do.
SECRET_PLAYBOOKS := homeautomation msmtp webservers

# SECRETS_LOADED marks the inner half of the re-entry; SECRETS=none skips it for a
# run that reaches no credential, usually a --tags run.
LOAD_SECRETS = $(if $(or $(SECRETS_LOADED),$(filter none,$(SECRETS))),,$(filter $*,$(SECRET_PLAYBOOKS)))

# SECRETS=none has to reach the play too: its pre_tasks assert that credentials
# arrived, and that assert must not outlive the decision to skip the injection.
SECRETS_FLAG = $(if $(filter none,$(SECRETS)),--extra-vars secrets_required=false)

# Prompt only when the run reaches the controller, the one host whose sudo asks. Asked of
# ansible rather than assumed, so a --limit in ARGS counts: one startup connecting to
# nothing, ~0.4s. Two ways to reach it, hence the two checks below: the host list, and a
# role with a become task under delegate_to.
list_run = ansible-playbook $(1).yml $(ARGS) --list-hosts --list-tasks 2>/dev/null

# Host names sit under "hosts (N):" and stop where the task list starts.
pick_hosts = awk '/hosts \([0-9]+\):/{f=1;next} /^[[:space:]]*tasks:/{f=0} /^[[:space:]]*$$/{f=0} f{gsub(/^[[:space:]]+|[[:space:]]+$$/,"");print}'

# Task lines read "  <role> : <name>", so the role is everything before " : ".
pick_roles = awk '/^[[:space:]]+[^ ]+ : /{sub(/ :.*/,"");gsub(/^[[:space:]]+/,"");print}' | sort -u

# IS_ROOT first: sudo asks root nothing, and ansible prompts at startup whether or not the
# password is used. Then ASK_PASS=1, which forces the prompt for a run the check below
# reads as needing none. `make faramir` is not one: the controller is in its first play,
# so that prompt also serves the second, which establishes the NOPASSWD the rest rely
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

# Close, escape, reopen. The forwarded arguments reach sops inside a command string,
# where one carrying a quote of its own would end the string early.
shquote = '$(subst ','\'',$(1))'

# A secret-bearing run whose store cannot be read is stopped rather than attempted: every
# secret_* would be undefined, and the first task to read one fails with the tasks before
# it already applied.
#
# The store's group holds no human, so only root and the broker's executor can serve such
# a run. Root covers all of it; the executor authenticates everywhere but has no sudo on
# the controller, hence the --limit in the second message.
#
# The `--` is repeated on the re-entry for the reason it is required on the way in.
#
# Only the first goal is applied: every inventory group is also a playbook here, so
# `make base -- --limit desktop` would otherwise apply desktop as well.
$(PLAYBOOKS): %: requirements
	@if [ "$*" != "$(firstword $(MAKECMDGOALS))" ]; then exit 0; fi; \
	 if [ -n "$(STRAY_ARGS)" ]; then \
	   echo "make read these as variable assignments rather than forwarding them:" >&2; \
	   echo "  $(STRAY_ARGS)" >&2; \
	   echo "An argument containing = never reaches ansible-playbook. Pass the whole" >&2; \
	   echo "list as one variable instead:" >&2; \
	   echo "  make $* ARGS='...'" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(LOAD_SECRETS)" ] && [ ! -r "$(SOPS_FILE)" ]; then \
	   echo "$(SOPS_FILE): not readable by $(OPERATOR)" >&2; \
	   echo "Refusing to run $*.yml: every secret_* variable would be undefined," >&2; \
	   echo "and the first task to read one fails with the tasks before it already" >&2; \
	   echo "applied. Run it as root, which reads the store and reaches every host:" >&2; \
	   echo "  sudo make $*$(if $(ARGS), -- $(ARGS))" >&2; \
	   echo "or through the broker, for every host but the controller:" >&2; \
	   echo "  faramir run --env-file faramir.env -- \\" >&2; \
	   echo "      ansible-playbook $*.yml --limit '!faramir'$(if $(ARGS), $(ARGS))" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(LOAD_SECRETS)" ]; then \
	   sops exec-env $(SOPS_FILE) $(call shquote,SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory $* -- $(ARGS)); \
	 else \
	   ansible-playbook $(call become_flag,$*) $(SECRETS_FLAG) $*.yml $(ARGS); \
	 fi
