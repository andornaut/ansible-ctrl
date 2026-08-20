# Every credential faramir.env names becomes an inventory variable of the same name, so
# host_vars can reference one without this repo holding a second mapping for it.
#
# The names come from faramir.env and the values from the environment. That file already
# lists every credential this repo uses, one per line, so that `faramir run --env-file` can
# inject them; reading the same list here is what makes the two routes agree on what a run
# should have. Only the left of each `=` is read, or the whole of a line that is just a
# name: the right is a faramir:// ref, and no value is ever in that file.
#
# A name rather than a prefix, because the names are the store's keys and `faramir://` has
# already said what they are. The cost is that a key faramir.env does not name is invisible
# here, which is the same thing as one list saying what this repo uses.
#
# A credential not in the environment is absent rather than empty, so the first task to use
# it fails naming it rather than applying a blank and reporting success. An empty value
# counts as absent for the same reason. The file itself is different: one that is not there
# stops the run naming it, because every credential coming back undefined otherwise reads
# as a broker that is not serving.
#
# These land at vars-plugin scope, which outranks host_vars and group_vars: ansible.cfg
# lists this after host_group_vars and the later plugin wins. So a host_vars entry under a
# name faramir.env declares is dead: the injected value replaces it silently. Give a
# per-host override a name of its own and map it, which is what the mapping is for.
#
# The file is looked for beside the playbook. An ad-hoc `ansible` run has no playbook and
# resolves that from the working directory, so one from elsewhere finds no file and reports
# every credential undefined. Run those from the repository root.
#
# The values arrive from `sops exec-env` or from the broker; nothing here reads the store.
# See the README.
from os import environ
from pathlib import Path

from ansible.errors import AnsibleParserError
from ansible.plugins.vars import BaseVarsPlugin

DOCUMENTATION = """
    name: faramir_env
    short_description: Expose the credentials faramir.env names as inventory variables
    description:
      - Returns every environment variable named on the left of an assignment in
        C(faramir.env), as a variable of the same name. Absent or empty variables
        are omitted, so referencing one that was never injected raises an
        undefined-variable error rather than resolving to a blank value.
      - A missing or unreadable C(faramir.env) is an error naming the file. One
        that is there and declares nothing is not.
      - Reads only the names from that file. The right of each assignment is a
        C(faramir://) reference and no credential value is ever held there.
      - Also returns C(secrets_injected), how many were found, so a play can
        require that credentials arrived without naming each one.
    options: {}
"""

# Beside the playbook, which is where `faramir run --env-file faramir.env` names it from.
ENV_FILE = "faramir.env"

# How many were injected, so a play can require that credentials arrived without naming each
# one: the whole env file arrives or nothing does, so one count answers for all.
#
# Not itself a credential name. This is a count and safe to print, and
# `ansible <host> -m debug -a 'var=secrets_injected'` tells an uninjected run from a
# misnamed reference.
COUNT_VAR = "secrets_injected"

# Parsed names by the directory they were read from. get_vars runs once per host per
# inventory source, and the file does not change inside a run.
_names_by_basedir = {}


def declared_names(basedir):
    """Every variable name faramir.env declares, in the order the file gives them.

    A file that is not there stops the run naming it, rather than yielding none: nothing
    else would say why, and every credential coming back undefined reads as a broker that
    is not serving. A file that is there and declares nothing is not an error, that being
    a repository which needs no credentials.
    """
    if basedir in _names_by_basedir:
        return _names_by_basedir[basedir]
    path = Path(basedir) / ENV_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise AnsibleParserError(
            f"{path} is not there, and it names the credentials this repository uses, "
            "so every one of them would be undefined. It is gitignored, so a fresh "
            "checkout has to be given one. An ad-hoc `ansible` command looks for it in "
            "the working directory rather than beside a playbook, so run those from the "
            "repository root."
        ) from None
    except (OSError, ValueError) as err:
        # ValueError covers UnicodeDecodeError: a file that is not text is a file
        # naming nothing, and silence there would read as no credentials declared.
        raise AnsibleParserError(f"{path} could not be read: {err}") from None
    names = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Both forms faramir's own --env-file takes: NAME=faramir://ref, and a line
        # that is only a name, which asks for the ref of that name.
        name = line.split("=", 1)[0].strip()
        if name:
            names.append(name)
    _names_by_basedir[basedir] = names
    return names


class VarsModule(BaseVarsPlugin):
    # The same for every host and group, so entities is not consulted.
    def get_vars(self, loader, path, entities, cache=True):
        super().get_vars(loader, path, entities)
        secrets = {}
        for name in declared_names(loader.get_basedir()):
            value = environ.get(name)
            if value:
                secrets[name] = value
        return {**secrets, COUNT_VAR: len(secrets)}
