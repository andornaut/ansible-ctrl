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
| app-entries                                                     | Desktop entry overrides from `dev_app_entry_overrides`, the same mechanism as the [desktop](../desktop/README.md) role's. Only where `desktop_environment` is set                                         |
| apt                                                             | Development tools and build headers: `git` and its helpers, `gh`, `adb`, `jq`, `shellcheck`, `snmp`, `wireshark`, the database clients, `-dev` packages                                                   |
| [claude](https://code.claude.com/docs)                          | AI coding assistant                                                                                                                                                                                       |
| [codex](https://github.com/openai/codex)                        | OpenAI Codex CLI. Not updated once installed: `codex` updates itself                                                                                                                                      |
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

| Variable                                       | Purpose                                                                                                                     |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `dev_install_*`                                | One flag per optional tool, default `false`                                                                                 |
| `dev_node_version`                             | Copies the `.nvmrc` pin of the JavaScript repositories                                                                      |
| `dev_ruby_version`, `dev_bundler_version`      | Copy the pins in mdtoc and til (`.ruby-version`, `Gemfile.lock`'s `BUNDLED WITH`). Raising one there does not raise it here |
| `dev_android_sdk_cmdline_tools_build`          | Build number of the Android command line tools archive, raised by hand: Google publishes no alias for the newest            |
| `dev_ai_maintainer_*`, `dev_ai_attributions_*` | Cron schedule, source directories and flags of the two cron jobs                                                            |
| `dev_ai_maintainer_project_script_path`        | Local ai-maintainer checkout that is symlinked when present, instead of a download                                          |

## ai-attributions

The cron entry runs `apply --push` with `dev_ai_attributions_apply_flags` across every checkout, printing nothing
when every repository is clean.

| Constraint      | Detail                                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------------------ |
| Signatures      | Re-emitted signed commits lose their signature                                                               |
| Backups         | `refs/ai-attributions-backup/<timestamp>/` holds the pre-rewrite refs of the last four runs                  |
| Dirty checkouts | A checkout with uncommitted tracked changes is reported and skipped                                          |
| Atomic push     | A protected tag, or a rolling tag the remote has moved, rejects the branch push too, and nothing is reported |
| Forks           | Skipped                                                                                                      |

## Notes

| Constraint           | Detail                                                                                                                     |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Android SDK location | `dev_android_sdk_root` (`~/Android/Sdk`), where Android Studio also looks. x86_64 only                                     |
| Two JDKs             | 21 answers a plain `java`. `android_sdk` sets `JAVA_HOME` to 17, which Gradle's Android plugin needs                       |
| chruby auto-switch   | A host without the exact Ruby `.ruby-version` names has nothing to switch to                                               |
| apt `nodejs`         | Kept alongside nvm for other users and the Ansible tasks, which do not source nvm                                          |
| Cursor sandbox       | A dedicated AppArmor profile grants it unprivileged user namespaces; the global restriction stays on                       |
| VirtualBox off       | Clearing `dev_install_virtualbox` removes the KVM blacklist. The VirtualBox packages and modules stay; remove them by hand |

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
