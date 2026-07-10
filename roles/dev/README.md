# ansible-role-dev

Installs development tools and programming languages on Ubuntu.

## Usage

```bash
make dev

ansible-playbook --ask-become-pass dev.yml --tags rust
```

## Tags

| Tag | Description |
| --- | --- |
| [ai_maintainer](https://github.com/andornaut/ai-maintainer) | Weekly cron job that runs the ai-maintainer script |
| [antigravity](https://antigravity.google/) | Google Antigravity IDE and CLI |
| [claude](https://docs.anthropic.com/en/docs/claude-code) | AI coding assistant |
| [codex](https://github.com/openai/codex) | OpenAI Codex CLI |
| [cursor](https://www.cursor.com/) | AI code editor (AppImage) |
| [filectrl](https://github.com/andornaut/filectrl) | File manager |
| [go](https://go.dev/) | Go toolchain |
| javascript | [Node.js](https://nodejs.org/) and [nvm](https://github.com/nvm-sh/nvm) |
| [kilocode](https://github.com/Kilo-Org/kilocode) | Kilo Code CLI and VS Code extension |
| [opencode](https://github.com/opencode-ai/opencode) | OpenCode AI tool |
| [python](https://www.python.org/) | Python 3 with pip, venv, pipenv, and [uv](https://github.com/astral-sh/uv) |
| [ruby](https://www.ruby-lang.org/) | Ruby with [chruby](https://github.com/postmodern/chruby) and [ruby-install](https://github.com/postmodern/ruby-install) |
| [rust](https://www.rust-lang.org/) | Rust toolchain via [rustup](https://rustup.rs/) |
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform with DKMS |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

Untagged apt packages (gh, git, [git-delta](https://github.com/dandavison/delta), jq, meld, wireshark, etc.) are
installed by [tasks/apt.yml](./tasks/apt.yml) on every run.

## Variables

See [defaults/main.yml](./defaults/main.yml). The `dev_ai_maintainer_*` vars configure the cron job and the
directory it operates on.

## Notes

- Cursor is granted unprivileged user namespaces by a dedicated AppArmor profile, rather than by disabling the
  restriction globally.
- The `ai_maintainer` tag runs only on hosts in the `ai_maintainer` inventory group. It installs a Sunday 3 AM
  cron job that runs [ai-maintainer](https://github.com/andornaut/ai-maintainer) to merge dependabot PRs, update
  dependencies, and fix test and CI failures across `~/src/github.com/andornaut/`. The script is symlinked from a
  local checkout when present, and downloaded otherwise.

## Operations

```bash
# Run ai-maintainer by hand
~/.local/bin/ai-maintainer --dry-run --verbose
```
