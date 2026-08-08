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
| [ai_maintainer](https://github.com/andornaut/ai-maintainer) | Weekly cron job that runs the ai-maintainer script, on hosts in the `ai_maintainer` group only |
| [antigravity](https://antigravity.google/) | Google Antigravity IDE and CLI |
| [claude](https://docs.anthropic.com/en/docs/claude-code) | AI coding assistant |
| [codex](https://github.com/openai/codex) | OpenAI Codex CLI |
| [cursor](https://www.cursor.com/) | AI code editor (AppImage) |
| [go](https://go.dev/) | Go toolchain |
| javascript | [Node.js](https://nodejs.org/) and [nvm](https://github.com/nvm-sh/nvm) |
| [kilocode](https://github.com/Kilo-Org/kilocode) | Kilo Code CLI and VS Code extension |
| [opencode](https://github.com/opencode-ai/opencode) | OpenCode AI tool |
| [python](https://www.python.org/) | Python 3 with pip, venv, pipenv, and [uv](https://github.com/astral-sh/uv) |
| [ruby](https://www.ruby-lang.org/) | Ruby with [chruby](https://github.com/postmodern/chruby) and [ruby-install](https://github.com/postmodern/ruby-install) |
| [rust](https://www.rust-lang.org/) | Rust toolchain via [rustup](https://rustup.rs/) |
| [sops](https://github.com/getsops/sops) | Encrypted file editor; it links [age](https://github.com/FiloSottile/age), so no age package is needed |
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform, from Oracle's apt repo, gated on `dev_install_virtualbox` |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

The apt packages in [tasks/apt.yml](./tasks/apt.yml) are untagged, and are installed on every run.

## Variables

See [defaults/main.yml](./defaults/main.yml). The `dev_ai_maintainer_*` vars configure the cron job and the
directory it operates on.

## Notes

- Cursor gets unprivileged user namespaces via a dedicated AppArmor profile, not by disabling the restriction
  globally.
- `ai_maintainer` symlinks [ai-maintainer](https://github.com/andornaut/ai-maintainer) from a local checkout
  (`dev_ai_maintainer_project_script_path`) when present, and downloads it otherwise.
- Setting `dev_install_virtualbox` back to `false` drops the KVM blacklist, so KVM works again. The VirtualBox
  packages and modules are left in place; remove them by hand.
- The `age` package is deliberately not installed. SOPS links the age library, and faramir mints keypairs with
  `faramir keygen`, so nothing here needs the binary.

## Operations

```bash
# Run ai-maintainer by hand
~/.local/bin/ai-maintainer --dry-run --verbose
```
