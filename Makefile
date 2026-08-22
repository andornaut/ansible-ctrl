SHELL := /bin/bash

# Arguments after `--` are forwarded verbatim to ansible-playbook; the separator is
# required, make rejecting bare --flags. See README.
#
# Every goal but the first, rather than every goal that is not the target: `make desktop
# -- --limit desktop` would otherwise drop the token from its own argument list.
GOAL_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
ARGS = $(GOAL_ARGS)

# Listed once: both readers below are silent about a name they do not know, one forwarding
# it to ansible-playbook and the other dropping it across the sudo re-entry.
KNOBS := SECRETS ASK_PASS PREFLIGHT ALLOW_ROOT

# An argument containing = never reaches ansible-playbook, make taking it as a variable
# assignment before the goal list is built. ARGS='...' is the route for one.
#
# Neither route combines with the other: a command-line ARGS outranks the goal-derived list
# and the %: rule below swallows the leftovers. Both cases land here and refuse the run.
ifeq ($(origin ARGS),command line)
STRAY_ARGS :=
DROPPED_ARGS := $(GOAL_ARGS)
else
STRAY_ARGS := $(filter-out $(addsuffix =%,$(KNOBS)),$(MAKEOVERRIDES))
DROPPED_ARGS :=
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

# A root run has HOME=/root, so the operator's home is resolved rather than named. Two
# sources, each covering the case the other gets wrong:
#
# FARAMIR_OPERATOR is the broker's own answer, set in a brokered command's environment and
# again in the one its sudo builds. The broker reserves the name, so a brokered caller
# cannot choose it, and it is the only source that survives that sudo.
#
# SUDO_USER is the operator wherever a human typed the sudo, which is every other root run
# here: `sudo make <playbook>`, and the re-entry below. It names the executor account
# instead on a brokered run -- the case FARAMIR_OPERATOR is there to answer, and which it
# answers first.
#
# Then whoever is running, which is already the answer for an unprivileged run, and for a
# root login with neither (cron), where it is root and nothing drops. getent rather than ~,
# which expands wrong for exactly the run that needs this.
OPERATOR := $(or $(FARAMIR_OPERATOR),$(and $(IS_ROOT),$(SUDO_USER)),$(shell id -un))
OPERATOR_HOME := $(shell getent passwd $(OPERATOR) | cut -d: -f6)

# Recipes write into the work tree as the operator, so a root run leaves nothing an
# unprivileged `make` cannot rebuild. A tree checked out by root resolves to root and
# nothing drops.
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
	@echo "  faramir               - Install the faramir secret broker on every faramir host,"
	@echo "                          then authorize the controller's SSH key on the managed hosts"
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
	@echo "  ALLOW_ROOT=1          - Run faramir as root, for a fleet that already authorizes its key"

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

# Both live under the operator's home and root's $HOME is /root, so each is named rather
# than found. ?= leaves an operator-set value alone.
#
# The broker's key is the identity that reaches the fleet, faramir.yml having authorized it
# there. Root's own ~/.ssh holds whatever it was given by hand, and offering an identity
# the fleet does not know fails host by host with the plays before it already applied. The
# operator's ssh config is still not read: it supplies aliases without an identity, and
# every ~ in it expands to /root.
#
# Host keys need no equivalent, roles/faramir pinning the fleet's in
# /etc/ssh/ssh_known_hosts, which ssh reads for every uid. The key is named only where it
# exists, ssh warning per host about an identity file it cannot open.
ifdef IS_ROOT
export SOPS_AGE_KEY_FILE ?= $(OPERATOR_HOME)/.config/faramir/age.key
ifneq ($(wildcard $(BROKER_KEY)),)
export ANSIBLE_PRIVATE_KEY_FILE ?= $(BROKER_KEY)
endif
endif

# The runs that read a credential, and so the only ones that re-enter under sops.
# Giving a playbook its first credential means adding it here. Not derived: host_vars binds
# plain variable names to secrets, so telling these apart needs variable resolution.
SECRET_PLAYBOOKS := homeautomation msmtp webservers

# SECRETS_LOADED marks the inner half of the re-entry; SECRETS=none skips it for a
# run that reaches no credential, usually a --tags run.
LOAD_SECRETS = $(if $(or $(SECRETS_LOADED),$(filter none,$(SECRETS))),,$(filter $*,$(SECRET_PLAYBOOKS)))

# SECRETS=none has to reach the play too: its pre_tasks assert that credentials
# arrived, and that assert must not outlive the decision to skip the injection.
SECRETS_FLAG = $(if $(filter none,$(SECRETS)),--extra-vars secrets_required=false)

# Which of this run's hosts the invoking account reaches, decided before any of it applies.
# A host the probe cannot reach is dropped through --limit, whatever stopped it: off,
# refusing the identity, a moved host key and a wedged sshd are all a host this run cannot
# apply to. A run left with no hosts stops. PREFLIGHT=none skips the probe.
#
# The --limit goes last and outranks one in ARGS, correctly: the list it is built from came
# from list_run, which already applied that one.
#
# raw, the question being whether ssh authenticates rather than whether python answers.
#
# Read from what failed, never from what succeeded: a success line carries the module's own
# output, whose shape differs per module, and a host whose line did not parse would be
# dropped without saying so.
RUN_PREFLIGHT = $(if $(filter none,$(PREFLIGHT)),,1)

# Every host that is up answers in well under a second, the site VPN included, so the
# timeout is paid only by hosts the probe cannot reach. 1 is the floor, --timeout and the
# ConnectTimeout it becomes taking whole seconds. It bounds the banner exchange too, so a
# host loaded enough to be slow answering is dropped rather than waited for.
PREFLIGHT_TIMEOUT := 1

# What this run resolves to, asked of ansible rather than assumed so a --limit in ARGS
# counts. One startup connecting to nothing, ~0.3s, and the recipe runs it once into $$run
# for both readers: the preflight, which probes the host list, and become_flag below.
list_run = ansible-playbook $(1).yml $(ARGS) --list-hosts --list-tasks 2>/dev/null

# Host names sit under "hosts (N):" and stop where the task list starts. Deduplicated: a
# host in two plays of one playbook is listed once per play.
pick_hosts = awk '/hosts \([0-9]+\):/{f=1;next} /^[[:space:]]*tasks:/{f=0} /^[[:space:]]*$$/{f=0} f{gsub(/^[[:space:]]+|[[:space:]]+$$/,"");if(!seen[$$0]++)print}'

# Task lines read "  <role> : <name>", so the role is everything before " : ".
pick_roles = awk '/^[[:space:]]+[^ ]+ : /{sub(/ :.*/,"");gsub(/^[[:space:]]+/,"");print}' | sort -u

# The name of each unreachable host, one per line. The callback renders a result as a
# block, "<host> | UNREACHABLE!" on the first line and the message indented under it, so
# only that line is read: why a host did not answer is the probe's business, not the
# operator's.
#
# No -o: it selects the oneline callback, and flag and callback alike are removed in
# ansible-core 2.23.
pick_unreachable = grep -E '^[^[:space:]]+ \| .*UNREACHABLE!' | cut -d' ' -f1

# IS_ROOT first: sudo asks root nothing, and ansible prompts at startup whether or not the
# password is used. Then ASK_PASS=1, which forces the prompt for a run the check below
# reads as needing none. `make faramir` is not one: the controller is in its first play, so
# that prompt also serves the second, which establishes the NOPASSWD the rest rely on.
#
# The controller group, not the faramir group, which also holds the hosts running a broker
# and no playbooks: those are NOPASSWD like the rest of the fleet, and prompting for a run
# that reaches one would ask for a password nothing uses.
#
# An empty answer prompts rather than passing over it. No playbook targets that group, so
# nothing else here fails when it is missing or misspelled, and the run that would otherwise
# go without the flag fails on the controller's sudo with the rest of the fleet applied.
#
# Reads $$run, which the recipe sets from list_run before reaching here.
define become_flag
$(if $(IS_ROOT),,$(if $(ASK_PASS),--ask-become-pass,$$( \
  controller=$$(ansible faramir_controller --list-hosts 2>/dev/null | $(pick_hosts)); \
  [ -z "$$controller" ] && { echo --ask-become-pass; exit 0; }; \
  echo "$$run" | $(pick_hosts) | grep -qxF "$$controller" && { echo --ask-become-pass; exit 0; }; \
  for r in $$(echo "$$run" | $(pick_roles)); do \
    grep -rqsE 'delegate_to:[[:space:]]*localhost' roles/$$r && { echo --ask-become-pass; exit 0; }; \
  done)))
endef

# Reads $$hosts, a comma-separated list, and sets $$limit to what survived. The probe runs
# as the account that will run the play, so it answers about the ~/.ssh that will connect.
define preflight
	       off=$$(ansible "$$hosts" -m raw -a true -T $(PREFLIGHT_TIMEOUT) 2>&1 | $(pick_unreachable)); \
	       if [ -n "$$off" ]; then \
	         for h in $$off; do echo "Preflight: dropped $$h (no connection)" >&2; done; \
	         reachable=$$(echo "$$hosts" | tr ',' '\n' | grep -vxF "$$off" | paste -sd,); \
	         if [ -z "$$reachable" ]; then \
	           echo "Preflight: nothing left to apply $*.yml to. A run connects with the" >&2; \
	           echo "invoking account's own ~/.ssh unless ANSIBLE_PRIVATE_KEY_FILE names an" >&2; \
	           echo "identity the fleet accepts, which this Makefile does for root, from the" >&2; \
	           echo "broker's key. Skip this check with PREFLIGHT=none." >&2; \
	           exit 1; \
	         fi; \
	         limit="--limit $$reachable"; \
	       fi;
endef

# Close, escape, reopen. The forwarded arguments reach sops inside a command string,
# where one carrying a quote of its own would end the string early.
shquote = '$(subst ','\'',$(1))'

# sudo resets the environment, and MAKEFLAGS goes with it, which is where make carries a
# command-line assignment down to a child. So each is named again, or `make homeautomation
# PREFLIGHT=none` probes anyway under root. The sops re-entry runs no sudo and needs none
# of this. An empty value is left out, every reader treating empty and unset alike.
REENTRY_VARS = $(foreach v,$(KNOBS),$(if $($(v)),$(v)=$(call shquote,$($(v)))))

# A secret-bearing run whose store the operator cannot read re-enters as root rather than
# being refused: every credential would otherwise be undefined, and the first task to read
# one fails with the tasks before it already applied. Root reads the store and reaches
# every host, the broker's key being the identity a root run connects with.
#
# Both re-entries hand the arguments over as ARGS rather than as goals: a command-line ARGS
# passes down through MAKEFLAGS and outranks anything the child derives from its own goals.
#
# Only the first goal is applied: every inventory group is also a playbook here, so
# `make base -- --limit desktop` would otherwise apply desktop as well.
# Ansible has no umask setting of its own, so every file a task creates without naming a
# mode arrives at whatever the invoking shell had. pam_umask gives a login shell the value
# in /etc/login.defs, which roles/base sets, and a session opened before that setting keeps
# the old one. Named here so a local run does not depend on which session started it; the
# same value, so a file created in a setgid share stays group-writable.
RUN_UMASK := 002

$(PLAYBOOKS): %: requirements
	@umask $(RUN_UMASK); \
	 if [ "$*" != "$(firstword $(MAKECMDGOALS))" ]; then exit 0; fi; \
	 if [ -n "$(STRAY_ARGS)" ]; then \
	   echo "make read these as variable assignments rather than forwarding them:" >&2; \
	   echo "  $(STRAY_ARGS)" >&2; \
	   echo "An argument containing = never reaches ansible-playbook. Pass the whole" >&2; \
	   echo "list as one variable instead:" >&2; \
	   echo "  make $* ARGS='...'" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(DROPPED_ARGS)" ]; then \
	   echo "ARGS was set on the command line, so these were dropped rather than" >&2; \
	   echo "forwarded:" >&2; \
	   echo "  $(DROPPED_ARGS)" >&2; \
	   echo "A command-line ARGS outranks the list built from what follows --. Pass" >&2; \
	   echo "the whole argument list as the one variable instead:" >&2; \
	   echo "  make $* ARGS='$(DROPPED_ARGS) ...'" >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(IS_ROOT)" ] && [ "$*" = faramir ] && [ -z "$(ALLOW_ROOT)" ]; then \
	   echo "Refusing to run faramir.yml as root: a root run connects with the" >&2; \
	   echo "broker's key, which is what this playbook authorizes. Run it as the" >&2; \
	   echo "operator, which connects with your own ~/.ssh:" >&2; \
	   echo "  make faramir" >&2; \
	   echo "On a fleet that already authorizes the key, ALLOW_ROOT=1 skips this." >&2; \
	   exit 1; \
	 fi; \
	 if [ -n "$(LOAD_SECRETS)" ] && [ ! -r "$(SOPS_FILE)" ]; then \
	   if [ -n "$(IS_ROOT)" ]; then \
	     echo "$(SOPS_FILE): not readable by root, so it is missing or its home is" >&2; \
	     echo "not mounted. Refusing to run $*.yml: every credential would be" >&2; \
	     echo "undefined, and the first task to read one fails with the tasks before" >&2; \
	     echo "it already applied." >&2; \
	     exit 1; \
	   fi; \
	   echo "$(SOPS_FILE) is not readable by $(OPERATOR), so this run re-enters as" >&2; \
	   echo "root, which reads the store and reaches every host." >&2; \
	   sudo $(SUBMAKE) --no-print-directory $* ARGS=$(call shquote,$(ARGS)) $(REENTRY_VARS); \
	 elif [ -n "$(LOAD_SECRETS)" ]; then \
	   sops exec-env $(SOPS_FILE) $(call shquote,SECRETS_LOADED=1 $(SUBMAKE) --no-print-directory $* ARGS=$(call shquote,$(ARGS))); \
	 else \
	   limit=""; \
	   run=$$($(call list_run,$*)); \
	   if [ -n "$(RUN_PREFLIGHT)" ]; then \
	     hosts=$$(echo "$$run" | $(pick_hosts) | paste -sd,); \
	     if [ -n "$$hosts" ]; then \
	       $(preflight) \
	     fi; \
	   fi; \
	   ansible-playbook $(become_flag) $(SECRETS_FLAG) $*.yml $(ARGS) $$limit; \
	 fi
