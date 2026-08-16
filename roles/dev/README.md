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
| [antigravity](https://antigravity.google/) | Google Antigravity IDE and CLI |
| [claude](https://docs.anthropic.com/en/docs/claude-code) | AI coding assistant |
| [codex](https://github.com/openai/codex) | OpenAI Codex CLI |
| [cursor](https://www.cursor.com/) | AI code editor (AppImage) |
| [go](https://go.dev/) | Go toolchain |
| java | [OpenJDK](https://openjdk.org/) 17 and 21 |
| javascript | [Node.js](https://nodejs.org/) and [nvm](https://github.com/nvm-sh/nvm) |
| [kilocode](https://github.com/Kilo-Org/kilocode) | Kilo Code CLI and VS Code extension |
| [opencode](https://github.com/opencode-ai/opencode) | OpenCode AI tool |
| pi | Two coding agents: [pi](https://github.com/badlogic/pi-mono) (`pi`) and [oh-my-pi](https://github.com/can1357/oh-my-pi) (`omp`), a fork of it |
| [python](https://www.python.org/) | Python 3 with pip, venv, pipenv, and [uv](https://github.com/astral-sh/uv) |
| [ruby](https://www.ruby-lang.org/) | Ruby with [chruby](https://github.com/postmodern/chruby) and [ruby-install](https://github.com/postmodern/ruby-install) |
| [rust](https://www.rust-lang.org/) | Rust toolchain via [rustup](https://rustup.rs/) |
| [sops](https://github.com/getsops/sops) | Encrypted file editor. No [age](https://github.com/FiloSottile/age) package is installed: sops links the library, and faramir mints keypairs with `faramir keygen` |
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform, from Oracle's apt repo, gated on `dev_install_virtualbox` |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

The apt packages in [tasks/apt.yml](./tasks/apt.yml) are untagged, so they are installed on every run
that names no `--tags`, and skipped by every run that does.

## Variables

See [defaults/main.yml](./defaults/main.yml). The `dev_ai_maintainer_*` and `dev_ai_attributions_*` vars
configure their cron jobs and the directories they operate on.

## Notes

| Tag | Constraint |
| --- | --- |
| ai_attributions | The binary comes from the project's newest version tag, through GitHub's latest-release redirect, so a run follows releases rather than every push to main. Verified against the release's `checksums.txt`, so a download straddling a publish fails rather than installing a mismatched binary. Pinning a version, or following the rolling `dev` release, is `dev_ai_attributions_release_url` and nothing else. The cron entry runs the scan with `--exit-code` and prints nothing when every repository is clean, so mail arrives only when something needs an answer, and each repository it reports comes with the `apply --push` command that fixes and publishes it. Forks are skipped by the tool. `git-filter-repo` is a system package rather than a dependency of this tag: scanning does not need it, the `apply` the scan suggests does, and that is run by hand on hosts where the scan is not scheduled |
| ai_maintainer | Symlinks [ai-maintainer](https://github.com/andornaut/ai-maintainer) from a local checkout (`dev_ai_maintainer_project_script_path`) when present, and downloads it otherwise |
| android_sdk | Installs to `dev_android_sdk_root` (`~/Android/Sdk`), where Android Studio also looks. Google names the command line tools archive after a build number with no stable alias for the newest, so `dev_android_sdk_cmdline_tools_build` pins it and has to be raised by hand. The archive expands to `cmdline-tools`, which sdkmanager requires be installed as `cmdline-tools/latest`, so it is unpacked to a temporary directory and moved. Licenses are accepted non-interactively: sdkmanager installs nothing until the hash files under `licenses/` exist, and only offers the prompt on a terminal |
| cursor | Unprivileged user namespaces come from a dedicated AppArmor profile, not from disabling the restriction globally |
| java | Two JDKs. 21 is Ubuntu's default and answers a plain `java`; 17 is what Gradle's Android plugin is built against, so `android_sdk` sets `JAVA_HOME` to 17. A Gradle build that picks the default JDK fails with a toolchain error naming the JDK it found |
| pi | Installs `pi` and `omp`, different binaries from different upstreams, which coexist. oh-my-pi is the release binary at `dev_oh_my_pi_binary_path`, not the npm package, which declares `engines.bun`. The binary is bun-compiled with the runtime inside it (~180MB) and its release asset name carries no version, so the task compares `omp --version` against the latest release tag and downloads only on a mismatch, verified against `SHA256SUMS.txt` |
| virtualbox | Clearing `dev_install_virtualbox` drops the KVM blacklist, so KVM works again. The VirtualBox packages and modules are left in place; remove them by hand |

Both cron entries live in `/etc/cron.d/ansible-role-dev`, rendered from one template. An entry appears only
where its flag is set, so clearing a flag drops its entry on the next run, and the file is removed where
neither is set.

## Operations

```bash
# Run ai-maintainer by hand
~/.local/bin/ai-maintainer --dry-run --verbose

# Run the attribution scan by hand, reporting every repository it reads rather
# than only the ones with a finding, which is what the cron entry asks for
~/.local/bin/ai-attributions scan --agents-files ~/src/github.com/andornaut/*

# Fix one repository and publish it, which is what the scan's summary suggests
~/.local/bin/ai-attributions apply --push ~/src/github.com/andornaut/<repo>

# Or rewrite without publishing, which prints the push command it did not run
~/.local/bin/ai-attributions apply ~/src/github.com/andornaut/<repo>

# Undo a rewrite
~/.local/bin/ai-attributions backups ~/src/github.com/andornaut/<repo>
~/.local/bin/ai-attributions restore <timestamp> ~/src/github.com/andornaut/<repo>
```
