# Every secret_* environment variable becomes an inventory variable of the same
# name, so host_vars can reference secret_msmtp_password without this repo
# holding a mapping for it.
#
# A credential that is not in the environment is absent rather than empty: the
# first task to use it fails naming it, instead of the run applying a blank
# credential and reporting success. An empty value counts as absent for the same
# reason.
#
# The values arrive from `sops exec-env` (make) or from the broker
# (`faramir run --env-file faramir.env`). Nothing here reads the store.
from os import environ

from ansible.plugins.vars import BaseVarsPlugin

DOCUMENTATION = """
    name: secret_env
    short_description: Expose secret_* environment variables as inventory variables
    description:
      - Returns every C(secret_*) environment variable as a variable of the same
        name. Absent or empty variables are omitted, so referencing one that was
        never injected raises an undefined-variable error rather than resolving
        to a blank value.
      - Also returns C(secrets_injected), how many were found, so a play can
        require that credentials arrived without naming each one.
    options: {}
"""

SECRET_PREFIX = "secret_"

# How many were injected, so a play can require that credentials arrived without
# naming every variable it might read. They arrive as a set: sops exec-env or the
# broker injects the whole env file or nothing does, so one count answers for all
# of them, and it answers the same on every host whatever that host references.
#
# Not prefixed secret_, which names a variable holding a credential. This holds a
# count, it is safe to print, and `ansible <host> -m debug -a 'var=secrets_injected'`
# is how to tell an uninjected run from a misnamed reference.
COUNT_VAR = "secrets_injected"


class VarsModule(BaseVarsPlugin):
    # The same for every host and group, so the entities are not consulted.
    def get_vars(self, loader, path, entities, cache=True):
        super().get_vars(loader, path, entities)
        secrets = {
            name: value
            for name, value in environ.items()
            if name.startswith(SECRET_PREFIX) and value
        }
        return {**secrets, COUNT_VAR: len(secrets)}
