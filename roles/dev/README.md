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
| [ai_maintainer](https://github.com/andornaut/ai-maintainer) | Weekly cron job that runs the ai-maintainer script |
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
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform with DKMS |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

The apt packages in [tasks/apt.yml](./tasks/apt.yml) are untagged, and are installed on every run.

## Variables

See [defaults/main.yml](./defaults/main.yml). The `dev_ai_maintainer_*` vars configure the cron job and the
directory it operates on.

## Notes

- Cursor gets unprivileged user namespaces via a dedicated AppArmor profile, not by disabling the restriction
  globally.
- The `ai_maintainer` tag runs only on hosts in the `ai_maintainer` inventory group. It installs a weekly cron job
  that runs [ai-maintainer](https://github.com/andornaut/ai-maintainer). The script is symlinked from a local
  checkout (`dev_ai_maintainer_project_script_path`) when present, downloaded otherwise.

## Operations

```bash
# Run ai-maintainer by hand
~/.local/bin/ai-maintainer --dry-run --verbose
```
