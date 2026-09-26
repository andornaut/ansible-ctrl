# ansible-role-dev

Installs development tools and programming languages on Ubuntu.

## Usage

```bash
make dev
make dev -- --tags rust
```

## Tags

| Tag                                                             | Description                                                                                                                                                                                               |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ai_attributions](https://github.com/andornaut/ai-attributions) | Daily cron job that rewrites every checkout's AI attributions and force-pushes them, gated on `dev_install_ai_attributions`. See [ai-attributions](#ai-attributions)                                      |
| [ai_maintainer](https://github.com/andornaut/ai-maintainer)     | Weekly cron job that runs the ai-maintainer script, gated on `dev_install_ai_maintainer`                                                                                                                  |
| [android_sdk](https://developer.android.com/tools)              | Android command line tools, platform and build-tools, gated on `dev_install_android_sdk`                                                                                                                  |
| [antigravity](https://antigravity.google/)                      | Google Antigravity IDE, gated on `dev_install_antigravity`, and the `agy` CLI, gated on `dev_install_antigravity_cli`                                                                                     |
| app-entries                                                     | Desktop entry overrides from `dev_app_entry_overrides`, the same mechanism as the [desktop](../desktop/README.md) role's. Overrides no longer named are removed. Only where `desktop_environment` is set  |
| apt                                                             | Development tools and the build headers other tags need: `git` and its helpers, `gh`, `adb`, `jq`, `shellcheck`, `snmp`, `wireshark`, the database clients, `-dev` packages                               |
| [claude](https://code.claude.com/docs)                          | AI coding assistant                                                                                                                                                                                       |
| [codex](https://github.com/openai/codex)                        | OpenAI Codex CLI                                                                                                                                                                                          |
| [cursor](https://cursor.com/)                                   | AI code editor (AppImage) and the `cursor-agent` CLI                                                                                                                                                      |
| [go](https://go.dev/)                                           | Go toolchain                                                                                                                                                                                              |
| java                                                            | [OpenJDK](https://openjdk.org/) 17 and 21                                                                                                                                                                 |
| javascript                                                      | [Node.js](https://nodejs.org/en) and [nvm](https://github.com/nvm-sh/nvm), with `dev_node_version` installed under `~/.nvm` and set as the default                                                        |
| [kilocode](https://github.com/Kilo-Org/kilocode)                | Kilo Code CLI and VS Code extension                                                                                                                                                                       |
| [opencode](https://github.com/anomalyco/opencode)               | OpenCode AI tool                                                                                                                                                                                          |
| pi                                                              | Two coding agents: [pi](https://github.com/earendil-works/pi) (`pi`) and [oh-my-pi](https://github.com/can1357/oh-my-pi) (`omp`), a fork of it                                                            |
| [python](https://www.python.org/)                               | Python 3 with pip, venv, pipenv, and [uv](https://github.com/astral-sh/uv)                                                                                                                                |
| [ruby](https://www.ruby-lang.org/)                              | Ruby with [chruby](https://github.com/postmodern/chruby), [ruby-install](https://github.com/postmodern/ruby-install), and `dev_ruby_version` built under `~/.rubies`, with [Bundler](https://bundler.io/) |
| [rust](https://rust-lang.org/)                                  | Stable Rust via [rustup](https://rustup.rs/), updated every run                                                                                                                                           |
| [virtualbox](https://www.virtualbox.org/)                       | Virtualization platform, from Oracle's apt repo, gated on `dev_install_virtualbox`                                                                                                                        |
| [vscode](https://code.visualstudio.com/)                        | Visual Studio Code                                                                                                                                                                                        |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                                       | Purpose                                                                            |
| ---------------------------------------------- | ---------------------------------------------------------------------------------- |
| `dev_install_*`                                | One flag per optional tool, default `false`                                        |
| `dev_node_version`, `dev_ruby_version`         | Copies of pins held in other repositories. See [Notes](#notes)                     |
| `dev_android_sdk_cmdline_tools_build`          | Build number of the Android command line tools archive, raised by hand             |
| `dev_ai_maintainer_*`, `dev_ai_attributions_*` | Cron schedule, source directories and flags of the two cron jobs                   |
| `dev_ai_maintainer_project_script_path`        | Local ai-maintainer checkout that is symlinked when present, instead of a download |
| `dev_app_entry_overrides`                      | Desktop entries to hide or recategorize                                            |

## Installed files

| Path                                                                    | Purpose                                                                                                      |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `/etc/cron.d/ansible-role-dev`                                          | The ai-attributions and ai-maintainer entries, each present only where its flag is. Removed where neither is |
| `/etc/apparmor.d/usr.local.bin.cursor`                                  | Grants the Cursor AppImage unprivileged user namespaces                                                      |
| `/usr/local/bin/cursor`, `/usr/local/share/applications/cursor.desktop` | The Cursor AppImage and its menu entry, which passes `--ozone-platform-hint=auto`                            |
| `/etc/modprobe.d/ansible-role-dev-blacklist-kvm.conf`                   | KVM blacklist, present only where `dev_install_virtualbox` is set                                            |
| `~/.local/bin/ai-attributions`, `~/.local/bin/ai-maintainer`            | The cron jobs' binaries                                                                                      |

## ai-attributions

| Constraint        | Detail                                                                                                                                                                                                                |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Release source    | The newest version tag, through GitHub's latest-release redirect, verified against that release's `checksums.txt`. The redirect skips the rolling `dev` release                                                       |
| Release URL       | `dev_ai_attributions_release_url` is a role var in [vars/main.yml](./vars/main.yml), not a host setting                                                                                                               |
| Output            | The cron entry runs `apply --push` with `dev_ai_attributions_apply_flags` (`--quiet --agents-files --emdashes`): nothing when every repository is clean, otherwise the rewrite it published for each one that was not |
| One run spans all | No `--base` is passed, so each ref is re-emitted from its earliest finding onward. Re-emitted signed commits lose their signature                                                                                     |
| Backups           | `refs/ai-attributions-backup/<timestamp>/` holds the pre-rewrite refs of the last four runs                                                                                                                           |
| Dirty checkouts   | A checkout with uncommitted tracked changes is reported and skipped; the rest still run                                                                                                                               |
| Atomic push       | One push per repository. A tag ruleset with `non_fast_forward` and no bypass actor, or a rolling tag the remote has moved, rejects the branch too, and nothing is reported                                            |
| Forks             | Skipped by the tool                                                                                                                                                                                                   |
| `git-filter-repo` | Required. Installed by the `apt` tag, not this one                                                                                                                                                                    |

## Notes

| Constraint             | Detail                                                                                                                                                                                                                                                                                                                                                    |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ai-maintainer source   | Symlinked from `dev_ai_maintainer_project_script_path` when that checkout exists, downloaded otherwise                                                                                                                                                                                                                                                    |
| Android SDK location   | `dev_android_sdk_root` (`~/Android/Sdk`), where Android Studio also looks                                                                                                                                                                                                                                                                                 |
| Command line tools pin | Google names the archive after a build number with no alias for the newest, so `dev_android_sdk_cmdline_tools_build` is raised by hand                                                                                                                                                                                                                    |
| `cmdline-tools/latest` | sdkmanager requires the archive installed at that path                                                                                                                                                                                                                                                                                                    |
| SDK licenses           | sdkmanager installs nothing until the hash files under `licenses/` exist. The role writes them by having sdkmanager accept every license                                                                                                                                                                                                                  |
| Codex install          | Upstream's standalone installer, run as `dev_user`: a self-contained binary at `~/.local/bin/codex`, no Node. `CODEX_NON_INTERACTIVE` answers no to its prompts                                                                                                                                                                                           |
| Codex updates          | Not updated once installed. `codex` updates itself, or re-run the installer                                                                                                                                                                                                                                                                               |
| Cursor sandbox         | Unprivileged user namespaces come from a dedicated AppArmor profile; the global restriction stays on                                                                                                                                                                                                                                                      |
| Node pin               | `dev_node_version` copies the `.nvmrc` pin of the JavaScript repositories                                                                                                                                                                                                                                                                                 |
| apt `nodejs`           | Kept alongside nvm: other users and the Ansible tasks use it, and neither sources nvm                                                                                                                                                                                                                                                                     |
| nvm default alias      | Written as `~/.nvm/alias/default`: `nvm alias default` reports no difference between a change and a no-op                                                                                                                                                                                                                                                 |
| Two JDKs               | 21 is Ubuntu's default and answers a plain `java`. 17 is what Gradle's Android plugin is built against, so `android_sdk` sets `JAVA_HOME` to 17                                                                                                                                                                                                           |
| Wrong JDK              | A Gradle build that picks the default JDK fails with a toolchain error naming the JDK it found                                                                                                                                                                                                                                                            |
| Ruby pins              | `dev_ruby_version` and `dev_bundler_version` copy the pins in mdtoc and til (`.ruby-version`, `Gemfile.lock`'s `BUNDLED WITH`). Raising one there does not raise it here                                                                                                                                                                                  |
| chruby auto-switch     | `auto.sh` switches to the Ruby under `~/.rubies` that `.ruby-version` names; a host without that exact version has nothing to switch to                                                                                                                                                                                                                   |
| Ruby build             | Runs as `dev_user` with `--no-install-deps`, the dependencies coming from the `apt` tag. Otherwise ruby-install calls `sudo apt-get` during the play                                                                                                                                                                                                      |
| `pi` and `omp`         | Different binaries from different upstreams, installed side by side                                                                                                                                                                                                                                                                                       |
| oh-my-pi binary        | The release binary at `dev_oh_my_pi_binary_path`, not the npm package, which declares `engines.bun`                                                                                                                                                                                                                                                       |
| oh-my-pi updates       | The asset name has no version, so `omp --version` is compared with the latest release tag and a mismatch downloads, verified against `SHA256SUMS.txt`                                                                                                                                                                                                     |
| Architectures          | `dev_arch` maps the kernel name to Debian's for the Antigravity, VS Code and VirtualBox apt repositories, the Go archive and `JAVA_HOME`. Cursor, ai-attributions and oh-my-pi name architectures their own way (`dev_cursor_platform`, `dev_ai_attributions_release_archive`, `oh_my_pi.yml`). The Android SDK is x86_64 only, asserted by `android_sdk` |
| VirtualBox off         | Clearing `dev_install_virtualbox` removes the KVM blacklist. The VirtualBox packages and modules stay; remove them by hand                                                                                                                                                                                                                                |

## Operations

```bash
# Run ai-maintainer by hand
~/.local/bin/ai-maintainer --dry-run --verbose

# Scan every repository, including output for clean ones that the cron entry's --quiet suppresses
~/.local/bin/ai-attributions scan --agents-files --emdashes ~/src/github.com/andornaut/*

# Fix one repository, with or without publishing (the second prints the push command)
~/.local/bin/ai-attributions apply --push ~/src/github.com/andornaut/<repo>
~/.local/bin/ai-attributions apply ~/src/github.com/andornaut/<repo>

# Undo a rewrite
~/.local/bin/ai-attributions backups ~/src/github.com/andornaut/<repo>
~/.local/bin/ai-attributions restore <timestamp> ~/src/github.com/andornaut/<repo>
```
