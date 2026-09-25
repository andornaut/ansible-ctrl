#!/usr/bin/env python3
"""Run a playbook the way every make target does.

Usage:
  bin/playbook.py run <playbook> [ansible-playbook arguments...]
  bin/playbook.py operator

Knobs are read from the environment, where make puts a command-line assignment:
SECRETS=none, ASK_PASS=1 and PREFLIGHT=none. See README.md, Usage.
"""

import os
import pwd
import re
import shlex
import signal
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parent.parent

# Every name a command-line assignment may take without being refused as a stray argument.
KNOBS = ("SECRETS", "ASK_PASS", "PREFLIGHT")

# The runs that require a credential, and so the only ones that re-enter as root or are
# refused to reach the store. Not derived: host_vars binds plain variable names to secrets,
# so telling these apart needs variable resolution.
SECRET_PLAYBOOKS = frozenset({"homeautomation", "msmtp", "webservers"})

# The hosts the unprivileged half listed, carried across the sudo re-entry so root does not
# list them again.
LISTED_HOSTS_ENV = "PLAYBOOK_LISTED_HOSTS"

# What the sudo re-entry names again, sudo resetting the environment.
CARRIED = (*KNOBS, LISTED_HOSTS_ENV)

# The exit status of a run whose probe dropped a host, whether or not the playbook applied
# to the rest: EX_TEMPFAIL, the host being expected back. Clear of ansible-playbook's own
# statuses, and outranked by them, a failed play being the more urgent news.
DROPPED_EXIT = 75

# Also passed with SECRETS=none: the play's pre_tasks assert that credentials arrived, and
# that assert must not outlive the decision to skip the injection.
SECRETS_OFF = ("--extra-vars", "secrets_required=false")

# The controller's sudo is answered by a person through faramir's PAM helper, and the local
# connection plugin's 10s default closes before anyone can. 120 rather than the 600 an
# escalation is offered for, so a run nobody is watching fails rather than holding the full
# window. Named here as well as on the controller's inventory line, which is not in this repo.
BECOME_PROMPT = ("--ask-become-pass", "-e", "ansible_local_become_success_timeout=120")

# The group whose one member is the controller.
CONTROLLER_GROUP = "faramir_controller"

# Whole seconds. Paid only by hosts that do not answer, and it bounds the banner exchange,
# so a host too loaded to answer promptly is dropped rather than waited for.
PREFLIGHT_TIMEOUT = "1"

# Ansible has no umask of its own, so a file a task creates without a mode takes the
# invoking shell's. The value roles/base sets, so a file in a setgid share stays
# group-writable whichever session started the run.
RUN_UMASK = 0o002

# The ansible-core floor README.md documents: the local connection gained
# ansible_local_become_success_timeout (BECOME_PROMPT) in 2.19.
MIN_ANSIBLE_CORE = (2, 19)

SOPS_FILE = ".config/faramir/secrets/ansible-ctrl.sops.yml"
AGE_KEY_FILE = ".config/faramir/age.key"
BROKER_KEY = ".config/faramir/id_ed25519"

HOSTS_HEADER = re.compile(r"hosts \([0-9]+\):")
TASKS_HEADER = re.compile(r"^\s*tasks:")
TASK_LINE = re.compile(r"^\s+[^ ]+ : ")
CORE_VERSION = re.compile(r"\[core ([0-9]+)\.([0-9]+)[^\]]*\]")
UNREACHABLE_LINE = re.compile(r"^\S+ \| .*UNREACHABLE!")
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
    and the only source that survives a brokered sudo. The certificate renewal cron sets it
    too, having no sudo to take the operator from. SUDO_USER is the operator wherever a human
    typed the sudo, and names the executor account on a brokered run, which is why it comes
    second. Otherwise whoever is running: an unprivileged run, or a root login with neither.
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


def secrets_route(
    playbook: str, env: Mapping[str, str], is_root: bool, readable: bool, decrypts: Callable[[], bool]
) -> tuple[str, str]:
    """How the run reaches its credentials, "none", "sops", "sudo" or "refuse", and what to
    tell the operator.

    readable is whether this account can read the store. Root that cannot is refused rather
    than run without: every credential would be undefined, and the first task to read one
    fails with the tasks before it already applied. Any other playbook reads only optional
    ones, github_token among them, so it never re-enters or escalates for the store, and
    takes it only where decrypts, called at most once, says sops can open it: a readable
    store without the age key, or without sops, would otherwise fail the run outright.
    """
    if is_none(env.get("SECRETS")):
        return "none", ""
    if playbook in SECRET_PLAYBOOKS:
        if readable:
            return "sops", ""
        return ("refuse" if is_root else "sudo"), ""
    if not readable:
        return "none", ""
    if decrypts():
        return "sops", ""
    return "none", (
        f"sops cannot decrypt the store, so {playbook}.yml runs without it and github_token is absent."
        " SECRETS=none silences this."
    )


def carried_hosts(env: Mapping[str, str], is_root: bool) -> list[str] | None:
    """The hosts the sudo re-entry carried, or None where this run lists its own.

    Root only, the re-entry being a sudo, so a value left in an operator's shell lists nothing
    away.
    """
    value = env.get(LISTED_HOSTS_ENV)
    if not is_root or not is_set(value):
        return None
    return value.strip().split(",")


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
            f"Preflight: nothing left to apply {playbook}.yml to.",
            "A run connects with the invoking account's own ~/.ssh, or the broker's key",
            "under root. Skip this check with PREFLIGHT=none.",
        ]
        return None, "\n".join(lines)
    # A root run connects with the key this playbook distributes, so a host that has yet to
    # authorize it reads as off, and the run would skip the host it was meant to configure.
    if is_root and playbook == "faramir":
        lines += [
            "A root run connects with the broker's key, which this playbook is what",
            "authorizes, so a host that has yet to authorize it reads the same as one",
            "that is off. Apply it as the operator: make faramir",
        ]
    return ["--limit", ",".join(reachable)], "\n".join(lines)


def listing_refusal(playbook: str, returncode: int, stderr: str, hosts: list[str]) -> str | None:
    """Why the listing stops the run, or None.

    Decided before the sudo re-entry and the become prompt, so an inventory or vars plugin
    error, or a --limit that matches nothing, is named before the operator is asked for a
    password or an escalation nothing would use. A listing reads no credential, the vars
    plugin leaving an uninjected one undefined and the play's assert not running.
    """
    if returncode != 0:
        return f"{stderr.rstrip()}\nListing the hosts of {playbook}.yml failed, so nothing was run."
    if not hosts:
        return f"No host matched {playbook}.yml's plays. Check hosts and any --limit; nothing was run."
    return None


def version_refusal(version_output: str) -> str | None:
    """Why the installed ansible-core stops the run, or None. Takes the output of
    `ansible-playbook --version`, whose first line reads "ansible-playbook [core X.Y.Z]"."""
    required = ".".join(map(str, MIN_ANSIBLE_CORE))
    match = CORE_VERSION.search(version_output.partition("\n")[0])
    if not match:
        return f"`ansible-playbook --version` named no ansible-core version. {required} or later is required."
    if (int(match.group(1)), int(match.group(2))) < MIN_ANSIBLE_CORE:
        installed = match.group(0)[len("[core ") : -1]
        return f"ansible-core {installed} is installed, and {required} or later is required. Nothing was run."
    return None


def exit_status(status: int, dropped: bool) -> int:
    """The run's exit status: the playbook's own where it failed, DROPPED_EXIT where it
    succeeded on what the probe left it. A playbook ended by a signal is 128 plus the
    signal's number, as a shell reports one."""
    if status < 0:
        return 128 - status
    return status or (DROPPED_EXIT if dropped else 0)


def sops_command(sops_file: str, argv: list[str]) -> list[str]:
    """argv under sops exec-env, which runs it through a shell, so every argument is quoted
    into one string. --same-process and the shell's exec leave ansible-playbook the process
    this one started, so a signal forwarded to it reaches the playbook."""
    return ["sops", "exec-env", "--same-process", sops_file, shlex.join(["exec", *argv])]


def sudo_command(env: Mapping[str, str], playbook: str, args: list[str]) -> list[str]:
    # sudo resets the environment, so each carried name is given again. Empty is left out,
    # every reader treating empty and unset alike.
    carried = [f"{k}={env[k]}" for k in CARRIED if is_set(env.get(k))]
    return ["sudo", *(["env", *carried] if carried else []), str(SCRIPT), "run", playbook, *args]


def sops_decrypts(sops_file: str) -> bool:
    """Whether sops can decrypt the store, with sops itself missing reading as no.

    true runs with the values in its environment and prints nothing, and sops's own output is
    discarded, so no value reaches this process.
    """
    try:
        probe = subprocess.run(
            ["sops", "exec-env", sops_file, "true"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return probe.returncode == 0


def capture(argv: list[str], *, stderr: int = subprocess.DEVNULL) -> str:
    return subprocess.run(argv, stdout=subprocess.PIPE, stderr=stderr, text=True, check=False).stdout


def capture_all(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def ansible_version() -> str:
    try:
        return capture(["ansible-playbook", "--version"])
    except OSError:
        return ""


def say(message: str) -> None:
    if message:
        print(message, file=sys.stderr, flush=True)


def run_child(argv: list[str]) -> int:
    """argv's exit status, waited for the way system(3) waits.

    SIGINT and SIGQUIT from the terminal reach the child through the foreground process
    group, so this process outlives them rather than leaving the child behind. SIGTERM and
    SIGHUP, sent to this process alone, are passed on. Installed before the child starts, as
    handlers rather than SIG_IGN, which exec would keep; one arriving before Popen returns is
    held and sent once it does.
    """
    child: subprocess.Popen[bytes] | None = None
    pending: list[int] = []

    def forward(signum: int, _frame: object) -> None:
        if child is None:
            pending.append(signum)
        else:
            child.send_signal(signum)

    def hold(_signum: int, _frame: object) -> None:
        pass

    handlers = {signal.SIGINT: hold, signal.SIGQUIT: hold, signal.SIGTERM: forward, signal.SIGHUP: forward}
    previous = {signum: signal.signal(signum, handler) for signum, handler in handlers.items()}
    try:
        child = subprocess.Popen(argv)
        for signum in pending:
            child.send_signal(signum)
        return child.wait()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


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

    # Listed ahead of the sudo re-entry, so a run the listing refuses asks for no password or
    # escalation first.
    run_hosts = carried_hosts(os.environ, root)
    roles: list[str] = []
    if run_hosts is None:
        stop = version_refusal(ansible_version())
        if stop:
            say(stop)
            return 1
        listed = capture_all(["ansible-playbook", f"{playbook}.yml", *args, "--list-hosts", "--list-tasks"])
        run_hosts = pick_hosts(listed.stdout)
        stop = listing_refusal(playbook, listed.returncode, listed.stderr, run_hosts)
        if stop:
            say(stop)
            return 1
        roles = pick_roles(listed.stdout)

    route, warning = secrets_route(
        playbook, os.environ, root, os.access(sops_file, os.R_OK), lambda: sops_decrypts(sops_file)
    )
    say(warning)
    if route == "refuse":
        say(
            f"{sops_file}: not readable by root, so it is missing or its home is\n"
            f"not mounted. Refusing to run {playbook}.yml: every credential would be undefined\n"
            "and the first task to read one fails with the rest already applied."
        )
        return 1
    if route == "sudo":
        say(f"Re-entering as root: {sops_file} is not readable by {account}.")
        argv = sudo_command({**os.environ, LISTED_HOSTS_ENV: ",".join(run_hosts)}, playbook, args)
        os.execvp(argv[0], argv)

    off: list[str] = []
    if not is_none(os.environ.get("PREFLIGHT")):
        # raw: the question is whether ssh authenticates, not whether python answers.
        probe = capture(
            ["ansible", ",".join(run_hosts), "-m", "raw", "-a", "true", "-T", PREFLIGHT_TIMEOUT],
            stderr=subprocess.STDOUT,
        )
        off = pick_unreachable(probe)
    limit, message = preflight_outcome(playbook, run_hosts, off, root)
    say(message)
    if limit is None:
        return DROPPED_EXIT

    flag = become_flag(
        root,
        os.environ.get("ASK_PASS"),
        lambda: pick_hosts(capture(["ansible", CONTROLLER_GROUP, "--list-hosts"])),
        run_hosts,
        roles,
        role_delegates_locally,
    )
    secrets_off = SECRETS_OFF if is_none(os.environ.get("SECRETS")) else ()
    argv = ["ansible-playbook", *flag, *secrets_off, f"{playbook}.yml", *args, *limit]
    if route == "sops":
        argv = sops_command(sops_file, argv)
    status = run_child(argv)
    # Said again, the first telling having scrolled away above the playbook's output.
    if message:
        say(f"{message}\n{playbook}.yml was not applied to the hosts named above.")
    return exit_status(status, bool(message))


def main(argv: list[str]) -> int:
    os.umask(RUN_UMASK)
    os.chdir(REPO)
    match argv:
        case ["operator"]:
            print(operator())
            return 0
        case ["run", playbook, *args]:
            # A Ctrl-C before the playbook starts, during the listing or a probe, exits the
            # way a signalled playbook does rather than with a traceback. run_child holds one
            # that arrives later.
            try:
                return run(playbook, args)
            except KeyboardInterrupt:
                return exit_status(-signal.SIGINT, False)
    print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
