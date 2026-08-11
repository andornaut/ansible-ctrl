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
| [antigravity](https://antigravity.google/) | Google Antigravity IDE and CLI |
| [claude](https://docs.anthropic.com/en/docs/claude-code) | AI coding assistant |
| [codex](https://github.com/openai/codex) | OpenAI Codex CLI |
| [cursor](https://www.cursor.com/) | AI code editor (AppImage) |
| [go](https://go.dev/) | Go toolchain |
| javascript | [Node.js](https://nodejs.org/) and [nvm](https://github.com/nvm-sh/nvm) |
| [kilocode](https://github.com/Kilo-Org/kilocode) | Kilo Code CLI and VS Code extension |
| [opencode](https://github.com/opencode-ai/opencode) | OpenCode AI tool |
| pi | Two coding agents: [pi](https://github.com/badlogic/pi-mono) (`pi`) and [oh-my-pi](https://github.com/can1357/oh-my-pi) (`omp`), a fork of it |
| [python](https://www.python.org/) | Python 3 with pip, venv, pipenv, and [uv](https://github.com/astral-sh/uv) |
| [ruby](https://www.ruby-lang.org/) | Ruby with [chruby](https://github.com/postmodern/chruby) and [ruby-install](https://github.com/postmodern/ruby-install) |
| [rust](https://www.rust-lang.org/) | Rust toolchain via [rustup](https://rustup.rs/) |
| [sops](https://github.com/getsops/sops) | Encrypted file editor; it links [age](https://github.com/FiloSottile/age), so no age package is needed |
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform, from Oracle's apt repo, gated on `dev_install_virtualbox` |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

The apt packages in [tasks/apt.yml](./tasks/apt.yml) are untagged, so they are installed on every run
that names no `--tags`, and skipped by every run that does.

## Variables

See [defaults/main.yml](./defaults/main.yml). The `dev_ai_maintainer_*` and `dev_ai_attributions_*` vars
configure their cron jobs and the directories they operate on.

## Notes

- Cursor gets unprivileged user namespaces via a dedicated AppArmor profile, not by disabling the restriction
  globally.
- `ai_maintainer` symlinks [ai-maintainer](https://github.com/andornaut/ai-maintainer) from a local checkout
  (`dev_ai_maintainer_project_script_path`) when present, and downloads it otherwise.
- `ai_attributions` installs the binary from the project's newest version tag, through GitHub's latest-release
  redirect, so a run follows releases rather than every push to its main branch. The download is verified
  against the release's `checksums.txt`, so one straddling a publish fails rather than installing a mismatched
  binary; pinning a version, or following the rolling `dev` release, is `dev_ai_attributions_release_url` and
  nothing else. Its cron entry runs the scan in `--exit-code` mode and prints nothing when every repository is
  clean, so mail arrives only when something needs an answer, and each repository it reports comes with the
  `apply --push` command that fixes and publishes it. Forks are skipped by the tool itself.
- Both cron entries live in `/etc/cron.d/ansible-role-dev`, rendered from one template. An entry appears only
  where its flag is set, so clearing a flag drops its entry on the next run, and the file is removed where
  neither is set.
- `git-filter-repo` is a system package rather than an `ai_attributions` dependency. Scanning does not need it,
  but the `apply` the scan suggests does, and that is run by hand on hosts where the scan is not scheduled.
- The `pi` tag installs both projects, which are different binaries (`pi` and `omp`) from different upstreams
  and coexist.
- oh-my-pi is installed as the release binary at `dev_oh_my_pi_binary_path`, not as the npm package, which
  declares `engines.bun` and runs under bun. The binary is bun-compiled with the runtime inside it and is
  ~180MB, and its release asset name carries no version, so the task compares `omp --version` against the
  latest release tag and downloads only on a mismatch. The download is verified against the release's
  `SHA256SUMS.txt`.
- Setting `dev_install_virtualbox` back to `false` drops the KVM blacklist, so KVM works again. The VirtualBox
  packages and modules are left in place; remove them by hand.
- The `age` package is deliberately not installed. SOPS links the age library, and faramir mints keypairs with
  `faramir keygen`, so nothing here needs the binary.

## Operations

```bash
# Run ai-maintainer by hand
~/.local/bin/ai-maintainer --dry-run --verbose

# Run the attribution scan by hand, reporting every repository it reads
~/.local/bin/ai-attributions-scan --verbose

# Fix one repository and publish it, which is what the scan's summary suggests
~/.local/bin/ai-attributions apply --push ~/src/github.com/andornaut/<repo>

# Or rewrite without publishing, which prints the push command it did not run
~/.local/bin/ai-attributions apply ~/src/github.com/andornaut/<repo>

# Undo a rewrite
~/.local/bin/ai-attributions backups ~/src/github.com/andornaut/<repo>
~/.local/bin/ai-attributions restore <timestamp> ~/src/github.com/andornaut/<repo>
```
