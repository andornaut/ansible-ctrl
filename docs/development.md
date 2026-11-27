# Development

The development checks need Docker, Bash, Git and Make.
Pinned stock Python 3.14 and Node 24.22.2 containers install the check dependencies in disposable scratch space.

```bash
make check                                     # Full local gate (also the default)
make lint                                      # Static checks in a container
make test                                      # Unit and task-identity checks in a container
make clean                                     # Remove local tooling and git hooks
```

`make check` runs all seven native checks in stock containers. Python installs the pinned tooling and Galaxy
collections, then runs Ansible lint, configuration validation, rendered-template ShellCheck, Ruff, task identity
and unit tests. Node installs the root npm lockfile and runs Markdown lint. The four Galaxy collections in
`requirements.yml` have no version pins.

Each language uses one non-root container with CPU, memory, file-descriptor and time limits. Dependency installation
has network access. Checks use a read-only copy of Git-visible inputs and writable container scratch; host homes,
Git metadata and ignored private files are not mounted.

| Check          | Covers                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `ansible-lint` | Ansible content                                                                                                                             |
| `config`       | `ansible.cfg` keys, since ansible ignores ones it does not recognize                                                                        |
| `shell`        | shellcheck on every shell script, templates rendered first                                                                                  |
| `python`       | `ruff check` and `ruff format --check`                                                                                                      |
| `identity`     | Every task that can change a host declares the account it runs as; read-only modules are exempt ([tests/identity.py](../tests/identity.py)) |
| `dispatch`     | Every `tests/test_*.py` but `test_identity.py`                                                                                              |
| `markdown`     | markdownlint on every `.md` file git does not ignore                                                                                        |

WORKAROUND: the Markdown CLI dependency overrides select patched Markdownlint and KaTeX versions for
[GHSA-gg6h-894w-4m9c](https://github.com/advisories/GHSA-gg6h-894w-4m9c) and
[GHSA-238p-pmpm-9mq7](https://github.com/advisories/GHSA-238p-pmpm-9mq7). Remove the overrides when the CLI
requires patched versions itself.

The [CI workflows](../.github/workflows) also run these jobs.

- **`check`** applies each Ubuntu playbook whose paths changed to the runner from role defaults
  ([tests/check/inventory.yml](../tests/check/inventory.yml)), skipping the tasks tagged `slow` so each entry fits in
  five minutes. `faramir`, `torrent`, `router`, `nas`, `rsnapshot` and `upgrade` are not covered, nor are the
  `bspwm` and `niri` roles.
- **`ai-attributions`** rejects commits carrying AI attribution or long dashes.
