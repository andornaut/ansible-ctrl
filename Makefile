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
STRAY_ARGS := $(filter-out SECRETS=% ASK_PASS=% PREFLIGHT=%,$(MAKEOVERRIDES))
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
	@echo "  PREFLIGHT=none        - Skip the reachability check, and attempt every host regardless"

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
BROKER_KEY := $(OPERATOR_HOME)/.config/faramir/id_ed25519

# sops looks for an identity under $HOME, and root's is /root, so the key is named. The
# keeper's key is already a recipient and root reads it whatever its mode. ?= leaves an
# operator-set value alone; the letsencrypt_nginx renewal cron names it for the same
# reason, being the other root-run entry point.
#
# ssh is named for the same reason. Root's own ~/.ssh holds whatever it was given by hand,
# which is not the fleet, and a run that offers an identity the fleet does not know fails
# host by host with the plays before it already applied. The broker's key is the identity
# that does reach every host: faramir.yml authorizes it fleet-wide, it carries no
# passphrase, and root reads it whatever its mode, so naming it here grants nothing root
# could not already do. The operator's ssh config is still not read: it supplies aliases
# without an identity, and every ~ in it expands to /root.
#
# Host keys need no equivalent. roles/faramir pins the fleet's in /etc/ssh/ssh_known_hosts,
# which ssh reads for every uid on this host, root included.
ifdef IS_ROOT
export SOPS_AGE_KEY_FILE ?= $(OPERATOR_HOME)/.config/faramir/age.key
export ANSIBLE_PRIVATE_KEY_FILE ?= $(BROKER_KEY)
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

# The other way to put a credential in a play's environment, for a secret-bearing run whose
# store the operator cannot read. Both halves have to be there: roles/faramir installs the
# binary, and faramir.env maps this repo's secret_* names onto the store's layout and is
# gitignored, so a checkout that was never enrolled has neither.
FARAMIR_ENV := faramir.env
BROKER_INSTALLED := $(if $(and $(shell command -v faramir 2>/dev/null),$(wildcard $(FARAMIR_ENV))),1)

# No --env-file: the probe asks whether ssh authenticates, which needs the executor's
# identity and none of the values, and injecting a credential into `true` would put
# plaintext in a process for nothing and an injection in the audit log for less.
BROKER_PROBE := $(if $(BROKER_INSTALLED),faramir run --)
BROKER_RUN := $(if $(BROKER_INSTALLED),faramir run --env-file $(FARAMIR_ENV) --)

# Whether to prove that whatever will run the play reaches this run's hosts before any of it
# applies -- the invoking uid, or the executor for the brokered half of a split run. A
# host that is down is dropped from the run through --limit, the play otherwise spending
# the connection timeout a second time to reach the conclusion the probe already reached.
# One that answers and refuses the connection stops the run instead. PREFLIGHT=none skips
# both, for a run that should attempt every host whatever the probe found.
#
# The --limit goes last and so outranks one in ARGS, which is correct rather than lossy:
# the host list it is built from comes from list_run, which already applied that one.
#
# raw, the question being whether ssh authenticates rather than whether python answers, and
# so needing neither an interpreter nor a module transfer. The timeout is the whole cost of
# the probe, every host that is up answering well inside a second, and it is not free to
# shorten: a host wrongly called down is dropped rather than merely reported.
#
# What survives is the probed list less what failed, never the lines that succeeded: those
# carry the module's own output, whose shape differs per module and per host, and a host
# whose line does not parse would be dropped from the run without saying so.
RUN_PREFLIGHT = $(if $(filter none,$(PREFLIGHT)),,1)

# The connection failures that mean a host is off and nothing more, which the preflight
# reports and carries on past. Anything else is an identity or a host key the fleet does
# not accept, a fault in the run rather than in the host. Kept in step with
# faramir_fleet_ping_offline_pattern in roles/faramir/defaults/main.yml, which sorts the
# broker's own fleet ping by the same rule.
PREFLIGHT_OFFLINE := Connection timed out|Connection refused|No route to host|Host is down

# What this run resolves to, asked of ansible rather than assumed so a --limit in ARGS
# counts. One startup connecting to nothing, ~0.3s, and the recipe runs it once into $$run
# for both readers: the preflight, which probes the host list, and become_flag below.
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
#
# Reads $$run, which the recipe sets from list_run before reaching here. Prompt or not, the
# playbook it describes is the one about to run.
define become_flag
$(if $(IS_ROOT),,$(if $(ASK_PASS),--ask-become-pass,$$( \
  controller=$$(ansible faramir --list-hosts 2>/dev/null | $(pick_hosts)); \
  for h in $$(echo "$$run" | $(pick_hosts)); do \
    for c in $$controller; do [ "$$h" = "$$c" ] && { echo --ask-become-pass; exit 0; }; done; \
  done; \
  for r in $$(echo "$$run" | $(pick_roles)); do \
    grep -rqsE 'delegate_to:[[:space:]]*localhost' roles/$$r && { echo --ask-become-pass; exit 0; }; \
  done)))
endef

# Why the identity that just failed to authenticate has the reach it has. One per caller of
# preflight below, which picks between them: a refusal that names the wrong identity sends
# the reader to the wrong file.
define preflight_hint_operator
	         echo "A run connects with the invoking account's own ~/.ssh unless" >&2; \
	         echo "ANSIBLE_PRIVATE_KEY_FILE names an identity the fleet accepts, which" >&2; \
	         echo "this Makefile does for root and root alone." >&2;
endef

define preflight_hint_broker
	         echo "A brokered run connects as the executor with the broker's key. Its" >&2; \
	         echo "public half is authorized fleet-wide by faramir.yml; a host that" >&2; \
	         echo "refuses it either sat out that run or has replaced the" >&2; \
	         echo "authorized_keys the play wrote. Re-run: make faramir" >&2;
endef

# Reads $$hosts, a comma-separated list, and $$who, what to call the identity in a refusal.
# Sets $$limit to what survived. $(1) prefixes the probe with whatever will run the play, so
# the question is put as the account that will connect: empty is the invoking one, and
# $(BROKER_PROBE) the executor. A probe put as the wrong account answers about the wrong
# ~/.ssh, which is worse than not probing.
define preflight
	       probe=$$($(1) ansible "$$hosts" -m raw -a true -o -T 3 2>&1); \
	       off=$$(echo "$$probe" | grep UNREACHABLE | grep -E '$(PREFLIGHT_OFFLINE)' | cut -d' ' -f1 | paste -sd' '); \
	       bad=$$(echo "$$probe" | grep UNREACHABLE | grep -vE '$(PREFLIGHT_OFFLINE)'); \
	       if [ -n "$$bad" ]; then \
	         echo "$$bad" >&2; \
	         echo "Preflight: refusing to run $*.yml, because $$who cannot" >&2; \
	         echo "authenticate to the hosts above, and ansible would find that out one" >&2; \
	         echo "host at a time, mid-run, with the plays before it already applied." >&2; \
	         $(if $(1),$(preflight_hint_broker),$(preflight_hint_operator)) \
	         echo "Skip this check with PREFLIGHT=none." >&2; \
	         exit 1; \
	       fi; \
	       if [ -n "$$off" ]; then \
	         reachable=$$(echo "$$hosts" | tr ',' '\n' | grep -vxF "$$(echo "$$off" | tr ' ' '\n')" | paste -sd,); \
	         for h in $$off; do echo "Preflight: dropped $$h (no connection)" >&2; done; \
	         if [ -z "$$reachable" ]; then \
	           echo "Preflight: nothing left to apply $*.yml to." >&2; \
	           exit 1; \
	         fi; \
	         limit="--limit $$reachable"; \
	       fi;
endef

# Close, escape, reopen. The forwarded arguments reach sops inside a command string,
# where one carrying a quote of its own would end the string early.
shquote = '$(subst ','\'',$(1))'

# A secret-bearing run whose store cannot be read is served rather than refused, where the
# broker is installed: every secret_* would otherwise be undefined, and the first task to
# read one fails with the tasks before it already applied.
#
# The store's group holds no human, so only root and the broker's executor can serve such a
# run, and they cover different hosts: root covers all of them, while the executor
# authenticates everywhere but has no sudo on the controller. So the run is split along that
# line rather than handed to one of them whole, and the halves are what each account can
# actually apply. Most such runs resolve to no controller at all -- webservers and
# homeautomation are remote groups -- and those go through the broker entire, with nothing
# to prompt for.
#
# The controller's half goes first, so its one sudo prompt is answered before the brokered
# half spends minutes on the fleet, and a refused password stops the run with nothing
# applied. Splitting costs the linear strategy's lockstep across the two halves, which none
# of SECRET_PLAYBOOKS depends on: each applies a per-host role. A playbook whose plays
# publish from one host and consume on another (faramir.yml) must not be added to that list
# without revisiting this.
#
# The `--` is repeated on both re-entries for the reason it is required on the way in.
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
	 if [ -n "$(IS_ROOT)" ] && [ "$*" = faramir ]; then \
	   echo "Refusing to run faramir.yml as root: it is what authorizes the key a" >&2; \
	   echo "root run connects with, so on a controller that has none there is no" >&2; \
	   echo "identity to reach the fleet with and the run fails host by host with" >&2; \
	   echo "the broker already installed. Run it as the operator:" >&2; \
	   echo "  make faramir" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(LOAD_SECRETS)" ] && [ ! -r "$(SOPS_FILE)" ] && [ -z "$(BROKER_INSTALLED)" ]; then \
	   echo "$(SOPS_FILE): not readable by $(OPERATOR)" >&2; \
	   echo "Refusing to run $*.yml: every secret_* variable would be undefined," >&2; \
	   echo "and the first task to read one fails with the tasks before it already" >&2; \
	   echo "applied. Run it as root, which reads the store and reaches every host:" >&2; \
	   echo "  sudo make $*$(if $(ARGS), -- $(ARGS))" >&2; \
	   echo "Installing the broker would let this run serve itself, splitting the" >&2; \
	   echo "fleet off to it and asking for a password only if the controller is in" >&2; \
	   echo "the run:" >&2; \
	   echo "  make faramir" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(LOAD_SECRETS)" ] && [ ! -r "$(SOPS_FILE)" ]; then \
	   run=$$($(call list_run,$*)); \
	   every=$$(echo "$$run" | $(pick_hosts)); \
	   controller=$$(ansible faramir --list-hosts 2>/dev/null | $(pick_hosts)); \
	   if [ -n "$$controller" ]; then \
	     ctrl=$$(echo "$$every" | grep -xF "$$controller" | paste -sd,); \
	     fleet=$$(echo "$$every" | grep -vxF "$$controller" | paste -sd,); \
	   else \
	     ctrl=""; \
	     fleet=$$(echo "$$every" | paste -sd,); \
	   fi; \
	   if [ -z "$$ctrl$$fleet" ]; then \
	     echo "$*.yml resolves to no hosts." >&2; \
	     exit 1; \
	   fi; \
	   echo "$(SOPS_FILE) is not readable by $(OPERATOR), so this run is split:" >&2; \
	   if [ -n "$$ctrl" ]; then echo "  $$ctrl -> as root, which reads the store" >&2; fi; \
	   if [ -n "$$fleet" ]; then echo "  $$fleet -> through the broker" >&2; fi; \
	   if [ -n "$$ctrl" ]; then \
	     sudo $(SUBMAKE) --no-print-directory $* -- $(ARGS) --limit "$$ctrl" || exit 1; \
	   fi; \
	   if [ -n "$$fleet" ]; then \
	     limit="--limit $$fleet"; \
	     if [ -n "$(RUN_PREFLIGHT)" ]; then \
	       hosts="$$fleet"; \
	       who="the broker's executor"; \
	       $(call preflight,$(BROKER_PROBE)) \
	     fi; \
	     $(BROKER_RUN) ansible-playbook $*.yml $(ARGS) $$limit; \
	   fi; \
	 elif [ -n "$(LOAD_SECRETS)" ]; then \
	   sops exec-env $(SOPS_FILE) $(call shquote,SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory $* -- $(ARGS)); \
	 else \
	   limit=""; \
	   run=$$($(call list_run,$*)); \
	   if [ -n "$(RUN_PREFLIGHT)" ]; then \
	     hosts=$$(echo "$$run" | $(pick_hosts) | paste -sd,); \
	     who=$$(id -un); \
	     if [ -n "$$hosts" ]; then \
	       $(call preflight,) \
	     fi; \
	   fi; \
	   ansible-playbook $(call become_flag,$*) $(SECRETS_FLAG) $*.yml $(ARGS) $$limit; \
	 fi
