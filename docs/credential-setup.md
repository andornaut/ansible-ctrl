# Credentials and secret broker

## Secrets

Credential values live in `~/.config/faramir/secrets/ansible-ctrl.sops.yml` ([sops](https://github.com/getsops/sops)
and [age](https://github.com/FiloSottile/age)). `faramir.env` (gitignored) lists their names, and each injected one
becomes a variable of that name. Map one to a differently named variable in `host_vars/`:

```yaml
homeautomation_esphome_password: "{{ esphome_password_example_site }}"
```

To add a credential, put the value in the store (`sudo faramir vault edit ansible-ctrl`, or `sudo faramir vault add
ansible-ctrl` while there is none), its name in `faramir.env`, and a mapping in `host_vars/` if needed.

| Gotcha                              | Detail                                                                                                               |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Injected names outrank `host_vars/` | A `host_vars/` entry under a name `faramir.env` declares is silently replaced. Give a per-host override its own name |
| `faramir.env` must exist            | A checkout without it stops the run. Run ad-hoc `ansible` commands from the repository root                          |
| `vars_plugins_enabled`              | [ansible.cfg](../ansible.cfg) must keep `host_group_vars` in the list, or `host_vars/` stops loading                 |

Credentials reach a play through `make` (under sops), the broker
(`faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir_controller'`), or the
certificate renewal cron. That `--limit` does not stop a task delegated to `localhost` with `become` (`games`'s
`retroid` tag, `base`'s lockdown when it moves an SSH port) from taking the controller's sudo. Run those through
`faramir run -- sudo make <playbook>`.

### GitHub API token

Optional. Without it, GitHub allows 60 API requests an hour per address, shared across the NAT; with it, 5000.

1. Create a fine-grained token with repository access _Public repositories_ and no permissions.
1. `sudo faramir vault edit ansible-ctrl` and add it as `github_token`.
1. Add `github_token` to `faramir.env`.

An expired token fails with HTTP 401. Use a dedicated token with the permissions above. If `gh` stores its token in the keyring,
`faramir link` cannot read it.

## Secret broker

[faramir](https://github.com/andornaut/faramir) runs credentialed commands without plaintext values reaching a
coding agent. See the [faramir role](../roles/faramir/README.md).

`make faramir` installs sops and the broker, and authorizes the broker's key and NOPASSWD sudo across the fleet.
Check with `faramir doctor`, `faramir status` and `faramir refs`, and end to end per
[Verification](../roles/faramir/README.md#verification).
