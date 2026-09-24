#!/usr/bin/env python3
"""Run a playbook the way every make target does.

Usage:
  bin/playbook.py run <playbook> [ansible-playbook arguments...]
  bin/playbook.py bootstrap --limit <host> [ansible-playbook arguments...]
  bin/playbook.py operator

Knobs are read from the environment, where make puts a command-line assignment:
SECRETS=none, ASK_PASS=1 and PREFLIGHT=none. See README.md, Usage.
"""

import ast
import os
import pwd
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parent.parent

# Every name a command-line assignment may take without being refused as a stray argument,
# and every name the sudo re-entry carries across, sudo resetting the environment.
KNOBS = ("SECRETS", "ASK_PASS", "PREFLIGHT")

# The runs that read a credential, and so the only ones that re-enter under sops. Not
# derived: host_vars binds plain variable names to secrets, so telling these apart needs
# variable resolution.
SECRET_PLAYBOOKS = frozenset({"homeautomation", "msmtp", "webservers"})

# Also passed with SECRETS=none: the play's pre_tasks assert that credentials arrived, and
# that assert must not outlive the decision to skip the injection.
SECRETS_OFF = ("--extra-vars", "secrets_required=false")

# The controller's sudo is answered by a person through faramir's PAM helper, and the local
# connection plugin's 10s default closes before anyone can. 120 rather than the 600 an
# escalation is offered for, so a run nobody is watching fails rather than holding the full
# window. Named here as well as on the controller's inventory line, which is not in this repo.
BECOME_PROMPT = ("--ask-become-pass", "-e", "ansible_local_become_success_timeout=120")

# Whole seconds. Paid only by hosts that do not answer, and it bounds the banner exchange,
# so a host too loaded to answer promptly is dropped rather than waited for.
PREFLIGHT_TIMEOUT = "1"

# Ansible has no umask of its own, so a file a task creates without a mode takes the
# invoking shell's. The value roles/base sets, so a file in a setgid share stays
# group-writable whichever session started the run.
RUN_UMASK = 0o002

# Applied ahead of every other playbook a bootstrap selects, in this order, each where it
# reaches the host. msmtp is named because its play targets every Ubuntu host rather than a
# group, which the selection below would otherwise pass over; dev because desktop's builds
# require the Go and Rust toolchains it installs.
BOOTSTRAP_FIRST = ("base", "docker", "msmtp", "dev")

# Never selected by a bootstrap. faramir.yml's second play reads the key its first play
# publishes on the controller, so a run limited to another host stops at its assert.
BOOTSTRAP_EXCLUDED = frozenset({"faramir"})

SOPS_FILE = ".config/faramir/secrets/ansible-ctrl.sops.yml"
AGE_KEY_FILE = ".config/faramir/age.key"
BROKER_KEY = ".config/faramir/id_ed25519"

HOSTS_HEADER = re.compile(r"hosts \([0-9]+\):")
TASKS_HEADER = re.compile(r"^\s*tasks:")
TASK_LINE = re.compile(r"^\s+[^ ]+ : ")
UNREACHABLE_LINE = re.compile(r"^\S+ \| .*UNREACHABLE!")
PLAY_PATTERN = re.compile(r"^\s*pattern: (\[.*\])\s*$")
DELEGATES_LOCALLY = re.compile(rb"delegate_to:[ \t\v\f\r]*localhost")


# make's reading of a value: $(if) strips whitespace before testing it, and $(filter) matches
# whole words.
def is_set(value: str | None) -> bool:
    return bool(value and value.strip())


def is_none(value: str | None) -> bool:
    return "none" in (value or "").split()


def stray_assignments(assignments: str) -> list[str]:
    return [w for w in assignments.split() if w.split("=", 1)[0] not in KNOBS]


def refusal(target: str, assignments: str, dropped: str) -> str | None:
    """Why this invocation would do something other than what was typed, or None."""
    stray = stray_assignments(assignments)
    if stray:
        return (
            "make read these as variable assignments rather than forwarding them:\n"
            f"  {' '.join(stray)}\n"
            "An argument containing = never reaches ansible-playbook. Pass them as one\n"
            "variable instead:\n"
            f"  make {target} ARGS='...'"
        )
    if dropped.strip():
        return (
            "ARGS was set on the command line, so these were dropped rather than\n"
            "forwarded:\n"
            f"  {dropped.strip()}\n"
            "A command-line ARGS outranks the list after --. Pass the whole list as\n"
            "that variable instead:\n"
            f"  make {target} ARGS='{dropped.strip()} ...'"
        )
    return None


def resolve_operator(env: Mapping[str, str], is_root: bool, whoami: str) -> str:
    """The account whose home holds the sops store and the broker's key.

    FARAMIR_OPERATOR is the broker's answer, reserved so a brokered caller cannot choose it,
    and the only source that survives a brokered sudo. SUDO_USER is the operator wherever a
    human typed the sudo, and names the executor account on a brokered run, which is why it
    comes second. Otherwise whoever is running: an unprivileged run, or a root login with
    neither (cron).
    """
    if is_set(env.get("FARAMIR_OPERATOR")):
        return env["FARAMIR_OPERATOR"].strip()
    if is_root and is_set(env.get("SUDO_USER")):
        return env["SUDO_USER"].strip()
    return whoami


# From the password database rather than ~, which expands to /root for exactly the run that
# needs this.
def home_of(user: str) -> str:
    try:
        return pwd.getpwnam(user).pw_dir
    except KeyError:
        return ""


def root_defaults(home: str, exists: Callable[[str], bool]) -> dict[str, str]:
    """What a root run names that an unprivileged one finds in its own home.

    The broker's key is the identity the fleet authorizes, faramir.yml having put it there;
    root's own ~/.ssh holds whatever it was given by hand. Named only where it exists, ssh
    warning per host about an identity file it cannot open. Host keys need nothing,
    /etc/ssh/ssh_known_hosts being read for every uid.
    """
    defaults = {"SOPS_AGE_KEY_FILE": f"{home}/{AGE_KEY_FILE}"}
    if exists(f"{home}/{BROKER_KEY}"):
        defaults["ANSIBLE_PRIVATE_KEY_FILE"] = f"{home}/{BROKER_KEY}"
    return defaults


def load_secrets(playbook: str, env: Mapping[str, str]) -> bool:
    if is_set(env.get("SECRETS_LOADED")) or is_none(env.get("SECRETS")):
        return False
    return playbook in SECRET_PLAYBOOKS


def pick_hosts(listing: str) -> list[str]:
    """Hosts under each "hosts (N):" header, in order, each once."""
    hosts: list[str] = []
    inside = False
    for line in listing.splitlines():
        if HOSTS_HEADER.search(line):
            inside = True
            continue
        if TASKS_HEADER.match(line) or not line.strip():
            inside = False
        if inside and line.strip() not in hosts:
            hosts.append(line.strip())
    return hosts


def pick_roles(listing: str) -> list[str]:
    """Roles of the tasks in a --list-tasks listing, whose lines read "<role> : <name>"."""
    return sorted({line.split(" :", 1)[0].strip() for line in listing.splitlines() if TASK_LINE.match(line)})


def pick_unreachable(output: str) -> list[str]:
    """Hosts the callback reported as "<host> | UNREACHABLE!".

    Read from what failed, never what succeeded: a success line carries the module's own
    output, and a host whose line did not parse would be dropped without saying so.
    """
    return [line.split(" ", 1)[0] for line in output.splitlines() if UNREACHABLE_LINE.match(line)]


def parse_plays(listing: str) -> list[tuple[list[str], list[str]]]:
    """Each play's host patterns and the hosts they resolved to, from --list-hosts."""
    plays: list[tuple[list[str], list[str]]] = []
    for block in re.split(r"\n\s*\n", listing):
        for line in block.splitlines():
            match = PLAY_PATTERN.match(line)
            if match:
                plays.append((list(ast.literal_eval(match.group(1))), pick_hosts(block)))
                break
    return plays


def names_a_group(patterns: Iterable[str]) -> bool:
    """Whether a play reaches its hosts through a named group rather than all of them."""
    terms = [t for p in patterns for t in re.split(r"[:,]", p) if t and t[0] not in "!&"]
    return bool(terms) and not any(t in {"all", "*"} for t in terms)


def select_bootstrap(listings: Mapping[str, str]) -> list[str]:
    """BOOTSTRAP_FIRST where it reaches the host, then each playbook with a group that does."""
    first = [pb for pb in BOOTSTRAP_FIRST if any(hosts for _, hosts in parse_plays(listings.get(pb, "")))]
    rest = [
        pb
        for pb in sorted(listings)
        if pb not in BOOTSTRAP_FIRST
        and pb not in BOOTSTRAP_EXCLUDED
        and any(hosts and names_a_group(p) for p, hosts in parse_plays(listings[pb]))
    ]
    return first + rest


def has_limit(args: Iterable[str]) -> bool:
    return any(a == "--limit" or a.startswith(("--limit=", "-l")) for a in args)


def become_flag(
    is_root: bool,
    ask_pass: str | None,
    controller: Callable[[], list[str]],
    run_hosts: list[str],
    roles: list[str],
    delegates_locally: Callable[[str], bool],
) -> tuple[str, ...]:
    """BECOME_PROMPT unless the run provably avoids the controller, the one host whose sudo asks.

    Root is asked nothing, and ansible prompts at startup whether or not the password is
    used. The controller group rather than faramir, whose other hosts are NOPASSWD. An empty
    group prompts: no playbook targets it, so a missing or misspelled one fails nowhere else
    and the run would fail on the controller's sudo with the rest of the fleet applied.
    """
    if is_root:
        return ()
    if is_set(ask_pass):
        return BECOME_PROMPT
    hosts = controller()
    if not hosts or any(h in run_hosts for h in hosts):
        return BECOME_PROMPT
    if any(delegates_locally(r) for r in roles):
        return BECOME_PROMPT
    return ()


def role_delegates_locally(role: str) -> bool:
    for root, _, files in os.walk(REPO / "roles" / role):
        for name in files:
            try:
                if DELEGATES_LOCALLY.search(Path(root, name).read_bytes()):
                    return True
            except OSError:
                continue
    return False


def preflight_outcome(playbook: str, hosts: list[str], off: list[str], is_root: bool) -> tuple[list[str] | None, str]:
    """The --limit to append (None to stop the run), and what to tell the operator.

    The --limit goes last and outranks one in the forwarded arguments, correctly: the host
    list came from a listing that already applied that one.
    """
    if not off:
        return [], ""
    lines = [f"Preflight: dropped {h} (no connection)" for h in off]
    reachable = [h for h in hosts if h not in off]
    if not reachable:
        lines += [
            f"Preflight: nothing left to apply {playbook}.yml to. A run connects with the",
            "invoking account's own ~/.ssh, or the broker's key under root.",
            "Skip this check with PREFLIGHT=none.",
        ]
        return None, "\n".join(lines)
    # A root run connects with the key this playbook distributes, so a host that has yet to
    # authorize it reads as off, and the run would skip the host it was meant to bootstrap.
    if is_root and playbook == "faramir":
        lines += [
            "A root run connects with the broker's key, which this playbook is what",
            "authorizes, so a host that has yet to authorize it reads the same as one",
            "that is off. Bootstrap it as the operator: make faramir",
        ]
    return ["--limit", ",".join(reachable)], "\n".join(lines)


def listing_refusal(playbook: str, returncode: int, stderr: str, hosts: list[str]) -> str | None:
    """Why the listing stops the run, or None.

    Decided before the become prompt, so an inventory or vars plugin error, or a --limit that
    matches nothing, is named before the operator is asked for a password nothing would use.
    """
    if returncode != 0:
        return f"{stderr.rstrip()}\nListing the hosts of {playbook}.yml failed, so nothing was run."
    if not hosts:
        return f"No host matched {playbook}.yml's plays. Check hosts and any --limit; nothing was run."
    return None


def sops_command(sops_file: str, playbook: str, args: list[str]) -> list[str]:
    # sops runs the command through a shell, so every argument is quoted into one string.
    inner = shlex.join(["SECRETS_LOADED=1", str(SCRIPT), "run", playbook, *args])
    return ["sops", "exec-env", sops_file, inner]


def sudo_command(env: Mapping[str, str], playbook: str, args: list[str]) -> list[str]:
    # sudo resets the environment, so each knob is named again. Empty is left out, every
    # reader treating empty and unset alike.
    knobs = [f"{k}={env[k]}" for k in KNOBS if is_set(env.get(k))]
    return ["sudo", *(["env", *knobs] if knobs else []), str(SCRIPT), "run", playbook, *args]


def capture(argv: list[str], *, stderr: int = subprocess.DEVNULL) -> str:
    return subprocess.run(argv, stdout=subprocess.PIPE, stderr=stderr, text=True, check=False).stdout


def capture_all(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def say(message: str) -> None:
    if message:
        print(message, file=sys.stderr, flush=True)


def is_root() -> bool:
    return os.geteuid() == 0


def operator() -> str:
    return resolve_operator(os.environ, is_root(), pwd.getpwuid(os.geteuid()).pw_name)


def refuse_invocation(target: str) -> bool:
    message = refusal(target, os.environ.get("PLAYBOOK_ASSIGNMENTS", ""), os.environ.get("PLAYBOOK_DROPPED_ARGS", ""))
    say(message or "")
    return message is not None


def run(playbook: str, args: list[str]) -> int:
    if refuse_invocation(playbook):
        return 1
    root = is_root()
    account = operator()
    home = home_of(account)
    if root:
        for key, value in root_defaults(home, os.path.exists).items():
            os.environ.setdefault(key, value)
    sops_file = f"{home}/{SOPS_FILE}"

    if load_secrets(playbook, os.environ):
        # Refused rather than run without: every credential would be undefined, and the
        # first task to read one fails with the tasks before it already applied.
        if not os.access(sops_file, os.R_OK):
            if root:
                say(
                    f"{sops_file}: not readable by root, so it is missing or its home is\n"
                    f"not mounted. Refusing to run {playbook}.yml: every credential would be undefined\n"
                    "and the first task to read one fails with the rest already applied."
                )
                return 1
            say(f"Re-entering as root: {sops_file} is not readable by {account}.")
            argv = sudo_command(os.environ, playbook, args)
        else:
            argv = sops_command(sops_file, playbook, args)
        os.execvp(argv[0], argv)

    listed = capture_all(["ansible-playbook", f"{playbook}.yml", *args, "--list-hosts", "--list-tasks"])
    listing = listed.stdout
    run_hosts = pick_hosts(listing)
    stop = listing_refusal(playbook, listed.returncode, listed.stderr, run_hosts)
    if stop:
        say(stop)
        return 1
    limit: list[str] = []
    if not is_none(os.environ.get("PREFLIGHT")) and run_hosts:
        # raw: the question is whether ssh authenticates, not whether python answers.
        probe = capture(
            ["ansible", ",".join(run_hosts), "-m", "raw", "-a", "true", "-T", PREFLIGHT_TIMEOUT],
            stderr=subprocess.STDOUT,
        )
        outcome, message = preflight_outcome(playbook, run_hosts, pick_unreachable(probe), root)
        say(message)
        if outcome is None:
            return 1
        limit = outcome

    flag = become_flag(
        root,
        os.environ.get("ASK_PASS"),
        lambda: pick_hosts(capture(["ansible", "faramir_controller", "--list-hosts"])),
        run_hosts,
        pick_roles(listing),
        role_delegates_locally,
    )
    secrets_off = SECRETS_OFF if is_none(os.environ.get("SECRETS")) else ()
    argv = ["ansible-playbook", *flag, *secrets_off, f"{playbook}.yml", *args, *limit]
    os.execvp(argv[0], argv)
    return 1


def bootstrap_env(env: Mapping[str, str]) -> dict[str, str]:
    """env with ASK_PASS forced: a fresh host's sudo asks until faramir.yml, which bootstrap
    never selects, writes the NOPASSWD rule. become_flag still asks root nothing."""
    return dict(env) if is_set(env.get("ASK_PASS")) else {**env, "ASK_PASS": "1"}


def bootstrap(args: list[str]) -> int:
    if refuse_invocation("bootstrap"):
        return 1
    if not has_limit(args):
        say("bootstrap applies every playbook that reaches a host, so it needs one named:")
        say("  make bootstrap -- --limit <host>")
        return 1
    playbooks = sorted(p.stem for p in REPO.glob("*.yml") if p.name != "requirements.yml")
    listings = {pb: capture(["ansible-playbook", f"{pb}.yml", *args, "--list-hosts"]) for pb in playbooks}
    selected = select_bootstrap(listings)
    if not selected:
        say(f"bootstrap: no playbook reaches {shlex.join(args)}")
        return 1
    say(f"bootstrap: {', '.join(selected)}")
    for index, playbook in enumerate(selected):
        status = subprocess.run(
            [sys.executable, str(SCRIPT), "run", playbook, *args], check=False, env=bootstrap_env(os.environ)
        ).returncode
        if status != 0:
            say(f"bootstrap: stopped at {playbook}.yml; not run: {', '.join(selected[index + 1 :]) or 'none'}")
            return status
    return 0


def main(argv: list[str]) -> int:
    os.umask(RUN_UMASK)
    os.chdir(REPO)
    match argv:
        case ["operator"]:
            print(operator())
            return 0
        case ["run", playbook, *args]:
            return run(playbook, args)
        case ["bootstrap", *args]:
            return bootstrap(args)
    print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
