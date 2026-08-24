# ansible-role-dev

Installs development tools and programming languages on Ubuntu.

## Usage

```bash
make dev
make dev -- --tags rust
```

## Tags

| Tag | Description |
| --- | --- |
| [ai_attributions](https://github.com/andornaut/ai-attributions) | Daily cron job that scans every checkout for AI attributions, gated on `dev_install_ai_attributions` |
| [ai_maintainer](https://github.com/andornaut/ai-maintainer) | Weekly cron job that runs the ai-maintainer script, gated on `dev_install_ai_maintainer` |
| [android_sdk](https://developer.android.com/tools) | Android command line tools, platform and build-tools, gated on `dev_install_android_sdk` |
| [antigravity](https://antigravity.google/) | Google Antigravity IDE, gated on `dev_install_antigravity`, and the `agy` CLI, gated on `dev_install_antigravity_cli` |
| apt | Development tools and the build headers other tags need: `git` and its helpers, `gh`, `adb`, `jq`, `shellcheck`, `snmp`, `wireshark`, and the database clients and `-dev` packages |
| [claude](https://code.claude.com/docs) | AI coding assistant |
| [codex](https://github.com/openai/codex) | OpenAI Codex CLI |
| [cursor](https://cursor.com/) | AI code editor (AppImage) |
| [go](https://go.dev/) | Go toolchain |
| java | [OpenJDK](https://openjdk.org/) 17 and 21 |
| javascript | [Node.js](https://nodejs.org/en) and [nvm](https://github.com/nvm-sh/nvm), with `dev_node_version` installed under `~/.nvm` and set as the default |
| [kilocode](https://github.com/Kilo-Org/kilocode) | Kilo Code CLI and VS Code extension |
| [opencode](https://github.com/opencode-ai/opencode) | OpenCode AI tool |
| pi | Two coding agents: [pi](https://github.com/earendil-works/pi) (`pi`) and [oh-my-pi](https://github.com/can1357/oh-my-pi) (`omp`), a fork of it |
| [python](https://www.python.org/) | Python 3 with pip, venv, pipenv, and [uv](https://github.com/astral-sh/uv) |
| [ruby](https://www.ruby-lang.org/) | Ruby with [chruby](https://github.com/postmodern/chruby), [ruby-install](https://github.com/postmodern/ruby-install), and `dev_ruby_version` built under `~/.rubies` with [Bundler](https://bundler.io/) |
| [rust](https://rust-lang.org/) | Rust toolchain via [rustup](https://rustup.rs/) |
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform, from Oracle's apt repo, gated on `dev_install_virtualbox` |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

## Variables

See [defaults/main.yml](./defaults/main.yml). The `dev_ai_maintainer_*` and `dev_ai_attributions_*` vars
configure their cron jobs and the directories they operate on.

## Notes

| Tag | Constraint |
| --- | --- |
| ai_attributions | The binary comes from the project's newest version tag, through GitHub's latest-release redirect, verified against that release's `checksums.txt`. `dev_ai_attributions_release_url` pins a version or follows the rolling `dev` release. The cron entry scans with `--quiet`, printing nothing when every repository is clean and the `apply --push` command for each one that is not. Forks are skipped by the tool. `git-filter-repo` is a system package rather than a dependency of this tag: scanning does not need it, the `apply` it suggests does |
| ai_maintainer | Symlinks [ai-maintainer](https://github.com/andornaut/ai-maintainer) from a local checkout (`dev_ai_maintainer_project_script_path`) when present, and downloads it otherwise |
| android_sdk | Installs to `dev_android_sdk_root` (`~/Android/Sdk`), where Android Studio also looks. Google names the command line tools archive after a build number with no stable alias for the newest, so `dev_android_sdk_cmdline_tools_build` pins it and has to be raised by hand. sdkmanager requires the archive be installed as `cmdline-tools/latest`, and installs nothing until the license hash files under `licenses/` exist, which the role writes directly |
| cursor | Unprivileged user namespaces come from a dedicated AppArmor profile, not from disabling the restriction globally |
| javascript | `dev_node_version` copies the pin the JavaScript repositories hold in `.nvmrc`. The apt `nodejs` is separate and stays: it serves other users and the Ansible tasks, neither of which sources nvm. The default alias is written as `~/.nvm/alias/default`, `nvm alias default` reporting no difference between a change and a no-op |
| java | Two JDKs. 21 is Ubuntu's default and answers a plain `java`; 17 is what Gradle's Android plugin is built against, so `android_sdk` sets `JAVA_HOME` to 17. A Gradle build that picks the default JDK fails with a toolchain error naming the JDK it found |
| ruby | `dev_ruby_version` and `dev_bundler_version` copy pins that live in mdtoc and til, in `.ruby-version` and in `Gemfile.lock`'s `BUNDLED WITH`. Raising one there does not raise it here. chruby's `auto.sh` switches to a Ruby under `~/.rubies` named by `.ruby-version`, so a host without that exact version has nothing to switch to. The build runs as `dev_user` with `--no-install-deps`, its dependencies coming from the apt task, because ruby-install otherwise calls `sudo apt-get` partway through the play |
| pi | `pi` and `omp` are different binaries from different upstreams, and coexist. oh-my-pi is the release binary at `dev_oh_my_pi_binary_path`, not the npm package, which declares `engines.bun`. Its release asset name carries no version, so the task compares `omp --version` against the latest release tag and downloads only on a mismatch, verified against `SHA256SUMS.txt` |
| virtualbox | Clearing `dev_install_virtualbox` drops the KVM blacklist. The VirtualBox packages and modules are left in place; remove them by hand |

Both cron entries live in `/etc/cron.d/ansible-role-dev`, rendered from one template. An entry appears only
where its flag is set, and the file is removed where neither is.

## Operations

```bash
# Run ai-maintainer by hand
~/.local/bin/ai-maintainer --dry-run --verbose

# Scan every repository, not only the ones with a finding as the cron entry does
~/.local/bin/ai-attributions scan --agents-files --emdashes ~/src/github.com/andornaut/*

# Fix one repository, with or without publishing (the second prints the push command)
~/.local/bin/ai-attributions apply --push ~/src/github.com/andornaut/<repo>
~/.local/bin/ai-attributions apply ~/src/github.com/andornaut/<repo>

# Undo a rewrite
~/.local/bin/ai-attributions backups ~/src/github.com/andornaut/<repo>
~/.local/bin/ai-attributions restore <timestamp> ~/src/github.com/andornaut/<repo>
```
