# ansible-ctrl

Provision Ubuntu workstations and servers with [Ansible](https://www.ansible.com/).

## Requirements

- Ubuntu >= 24.04
- Ansible >= 2.18, from the [Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible):

  ```bash
  sudo add-apt-repository --yes --update ppa:ansible/ansible
  sudo apt install ansible
  ```

## Usage

Every root `.yml` except `requirements.yml` is a playbook with a [make](Makefile) target of the same name. The
target installs dependencies, then runs `ansible-playbook <playbook>.yml`. Arguments after `--` are forwarded
to `ansible-playbook`.

```bash
make help                                        # List the targets
make desktop                                     # Run a playbook
make desktop -- --tags alacritty --limit example # Forward arguments
```

`--ask-become-pass` is added only when the run reaches the controller, which is the only host whose sudo asks
for a password: either it is in the play's host list, or a role in the run has a `become` task under
`delegate_to: localhost`. `ASK_PASS=1` forces the prompt.

`make ai_maintainer` is the exception: it is a tag in the [dev](roles/dev/README.md) role rather than a playbook,
so the target runs `dev.yml --tags ai_maintainer`.

## Roles

| Role | Purpose |
| --- | --- |
| [base](roles/base/README.md) | Base packages and system configuration, applied to every host |
| [bspwm](roles/bspwm/README.md) | BSPWM window manager and X11 utilities |
| [desktop](roles/desktop/README.md) | Desktop environment (display manager, browser, fonts, themes) |
| [dev](roles/dev/README.md) | Development tools and programming languages |
| [docker](roles/docker/README.md) | Docker CE and Compose, optional Kubernetes and Docker Registry |
| [faramir](roles/faramir/README.md) | Secret broker, so an agent can run credentialed commands without seeing the values |
| [games](roles/games/README.md) | Gaming packages via flatpak, and RetroArch (cores, BIOS, settings, playlists) |
| [hobbies](roles/hobbies/README.md) | 3D printing, electronics, FPV tools |
| [homeautomation](roles/homeautomation/README.md) | Home Assistant and related Docker containers |
| [letsencrypt_nginx](roles/letsencrypt_nginx/README.md) | NGINX reverse proxy with Let's Encrypt HTTPS |
| [msmtp](roles/msmtp/README.md) | Email forwarding via MSMTP |
| [nas](roles/nas/README.md) | Encrypted BTRFS RAID arrays (LUKS) |
| [niri](roles/niri/README.md) | Niri Wayland compositor and Wayland utilities |
| [rsnapshot](roles/rsnapshot/README.md) | Incremental backups with rsnapshot |
| [torrent](roles/torrent/README.md) | rtorrent on the remote host, plus torrent scripts and cron jobs on the controller |

Most playbooks apply one role to one group. The exceptions:

| Playbook | Behaviour |
| --- | --- |
| [desktop.yml](desktop.yml) | Applies `desktop` to the whole `desktop` group, then `bspwm` or `niri` per host's `desktop_environment` |
| [docker.yml](docker.yml) | Applies `docker` to `dev`, `homeautomation` and `webservers` in one run |
| [webservers.yml](webservers.yml) | Applies the `letsencrypt_nginx` role, which does not share the playbook's name |
| [faramir_fleet.yml](faramir_fleet.yml) | Uses no role: authorizes the broker's SSH key and a NOPASSWD sudoers entry on the managed hosts |
| [torrent.yml](torrent.yml) | Applies `torrent` to the `torrent` group, and in the same run delegates the `mvt`/`orgt`/`synct`/`unrart` scripts and cron jobs to the controller (the implicit localhost) |
| [upgrade.yml](upgrade.yml) | Uses no role: apt dist-upgrade and flatpak upgrade |

## Inventory

| Path | Contents |
| --- | --- |
| `hosts` (gitignored) | The inventory. Its group names are the `hosts:` field of each playbook |
| `host_vars/<hostname>.yml` (gitignored) | Per-host overrides: feature flags (`{role}_install_{component}`), Docker image tags, extra volumes |
| `group_vars/all/vars.yml` (gitignored) | Maps each credential name to `lookup('env', ...)`. Holds no values |
| `/etc/faramir/secrets/ansible-ctrl.sops.yml` (outside this repo) | Every credential value, and nothing else. See [Secrets](#secrets) |
| `roles/<role>/defaults/main.yml` | Role defaults. Override them in `host_vars/`, not here |

```ini
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[desktop]
example

[dev]
example
```

## Secrets

Every credential (API tokens, SMTP passwords, camera RTSP passwords, Home Assistant long-lived
tokens) lives in `/etc/faramir/secrets/ansible-ctrl.sops.yml`, encrypted with
[sops](https://github.com/getsops/sops) and age, and named `secret_<purpose>`. `host_vars/` holds
no credential values, only references to them:

```yaml
# host_vars/example.yml
msmtp_password: "{{ secret_msmtp_password }}"
```

`group_vars/all/vars.yml` binds the two. It maps each name to the environment and holds no value
itself:

```yaml
secret_msmtp_password: "{{ lookup('env', 'secret_msmtp_password') }}"
```

The split keeps `host_vars/` readable and diffable while the values are encrypted at rest, and it
means a value only ever reaches a play through the environment. Two things put it there. `make`
wraps itself in `sops exec-env` when the values are not already loaded, which needs the age
identity at `~/.config/sops/age/keys.txt`. The [faramir](roles/faramir/README.md) broker supplies
the same names to a command that never sees them:

```bash
faramir run --env-file faramir.env -- ansible-playbook homeautomation.yml --limit '!faramir'
```

`faramir.env` holds no values, only `secret://` references, and is gitignored anyway: those
references map this repo's variable names onto the secret store's layout. Adding a credential is
four edits: the value into the sops file, the `lookup('env', ...)` mapping into
`group_vars/all/vars.yml`, the ref into `faramir.env`, and the reference into `host_vars/`.

The certificate renewal cron is the third path, and wraps itself.
[roles/letsencrypt_nginx/tasks/cron.yml](roles/letsencrypt_nginx/tasks/cron.yml) runs
`ansible-playbook` under `sops exec-env` directly rather than through `make`, which would add
`--ask-become-pass` on a run that reaches the controller and leave cron with a prompt and no
terminal. It decrypts with `/etc/faramir/age.key`, the keeper's, which is already a recipient and
which root can read anyway.

**Why the file is under `/etc` and not in this repo.** Cron has no session and the broker starts at
boot, and an encrypted home is not mounted at either moment, so anything under one is unreadable
exactly when these need it: the cron would fail at the `cd` and the broker would come up with an
empty value set, redacting nothing. `/etc/faramir/secrets` is `2770 root:dev`, so you still edit it
with `sops` directly, without sudo. It also keeps the ciphertext out of a directory Ansible
auto-loads, where a sops file, being valid YAML, would bind each var to its `ENC[...]` ciphertext
without erroring and hand hosts the ciphertext as the password.

The encrypted file and the age identity both need a backup and neither is in git. Both are covered
by rsnapshot today: it takes `/etc/` and `~/.config/`. Note that this puts the key and the
ciphertext it opens in the same snapshot.

## Getting started with the secret broker

[faramir](https://github.com/andornaut/faramir) runs commands that need credentials without any
plaintext value entering a coding agent's context. It is what lets an agent run these playbooks
against the fleet without being able to read the credentials they use. The
[faramir role](roles/faramir/README.md) installs it on the controller; faramir's own
[README](https://github.com/andornaut/faramir#readme) explains what it protects against, which is
worth reading before trusting it.

Installing it is an operator action, run against the controller. Brokering playbooks is an agent
action, run later. Ansible never needs faramir in order to run, so none of the above depends on
this.

**1. Clone faramir beside this repo** and make sure the [dev](roles/dev/README.md) role has run,
which is what installs Go and sops:

```bash
git clone git@github.com:andornaut/faramir.git ~/src/github.com/andornaut/faramir
make dev
```

**2. Install it.** The role builds the binaries from that checkout, then runs faramir's own install
phases as root, so this is the one target that asks for a sudo password:

```bash
make faramir
```

**3. Log out and back in.** The install adds you to the `dev` group, and group membership is read
at login. Until then the broker refuses your connections.

**4. Check what it loaded:**

```bash
faramir status          # config path, the sops files it manages, and the ref count
faramir list-secrets    # the names, never the values
```

A ref count of zero means the broker is running and protecting nothing, so treat it as a failure
rather than a fresh start.

**5. Authorize its SSH key on the managed hosts**, which is what lets a brokered playbook reach
them. `ASK_PASS=1` is required because this is the run that establishes the NOPASSWD sudo the
others rely on:

```bash
make faramir_fleet ASK_PASS=1
```

**6. Prove the whole chain end to end**, which is one command:

```bash
faramir run --env-file faramir.env -- \
    ansible <host> -m debug -a 'var=secret_msmtp_password'
# -> "secret_msmtp_password": "«SECRET:secret_msmtp_password»"
```

That confirms the ref decrypted, the value reached the child's environment, `lookup('env', ...)`
resolved it, and the redactor replaced it on the way back. A bare name means the ref was not
injected; `ENC[AES256_GCM,...]` means the encrypted file is somewhere Ansible auto-loads it.

After that, an agent runs playbooks through the broker rather than through `make`:

```bash
faramir run --env-file faramir.env -- \
    ansible-playbook <playbook>.yml --limit '!faramir'
```

`--limit '!faramir'` excludes the controller, which a brokered run cannot configure: commands run
as a uid with no sudo there. The controller's own playbooks stay yours to apply.

## Operations

[.github/workflows/lint.yml](.github/workflows/lint.yml) runs on every pull request: `ansible-lint`,
`syntax-check`, `shellcheck` (every shell script under `roles/`, discovered by shebang), and `python-syntax`
(every Python file under `roles/*/files/`). The first two are reproducible locally:

```bash
# Lint
python3 -m venv /tmp/ansible-lint-venv \
    && /tmp/ansible-lint-venv/bin/pip install ansible-lint \
    && /tmp/ansible-lint-venv/bin/ansible-lint

# Syntax-check every playbook. The real inventory is gitignored, so parse against the committed CI one.
for pb in *.yml; do [ "$pb" = requirements.yml ] && continue; \
    ansible-playbook --syntax-check -i tests/inventory.ini "$pb"; done

# Upgrade all collections, which `make requirements` does not do
ansible-galaxy collection install --upgrade -r requirements.yml

# Remove downloaded roles and collections
make clean
```
