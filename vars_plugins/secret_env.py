# Every secret_* environment variable becomes an inventory variable of the same name,
# so host_vars can reference one without this repo holding a mapping for it.
#
# A credential not in the environment is absent rather than empty, so the first task
# to use it fails naming it rather than applying a blank and reporting success. An
# empty value counts as absent for the same reason.
#
# The values arrive from `sops exec-env` or from the broker; nothing here reads the
# store. See the README.
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
# naming each one: the whole env file arrives or nothing does, so one count answers
# for all of them, on every host.
#
# Not prefixed secret_, which names a credential. This is a count and safe to print,
# and `ansible <host> -m debug -a 'var=secrets_injected'` tells an uninjected run
# from a misnamed reference.
COUNT_VAR = "secrets_injected"


class VarsModule(BaseVarsPlugin):
    # The same for every host and group, so entities is not consulted.
    def get_vars(self, loader, path, entities, cache=True):
        super().get_vars(loader, path, entities)
        secrets = {
            name: value
            for name, value in environ.items()
            if name.startswith(SECRET_PREFIX) and value
        }
        return {**secrets, COUNT_VAR: len(secrets)}
