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
| [ai_maintainer](https://github.com/andornaut/ai-maintainer) | Automated GitHub repo maintenance via AI agent + cron (see below) |
| [antigravity](https://antigravity.google/) | Google Antigravity IDE and CLI |
| [claude](https://docs.anthropic.com/en/docs/claude-code) | AI coding assistant |
| [codex](https://github.com/openai/codex) | OpenAI Codex CLI |
| [cursor](https://www.cursor.com/) | AI code editor (AppImage) |
| [delta](https://github.com/dandavison/delta) | Syntax-highlighting diff viewer for git |
| [filectrl](https://github.com/andornaut/filectrl) | File manager |
| [go](https://go.dev/) | Go toolchain |
| javascript | [Node.js](https://nodejs.org/) and [nvm](https://github.com/nvm-sh/nvm) |
| [opencode](https://github.com/opencode-ai/opencode) | OpenCode AI tool |
| [python](https://www.python.org/) | Python 3 with pip, venv, pipenv |
| [ruby](https://www.ruby-lang.org/) | Ruby with [chruby](https://github.com/postmodern/chruby) and [ruby-install](https://github.com/postmodern/ruby-install) |
| [rust](https://www.rust-lang.org/) | Rust toolchain via [rustup](https://rustup.rs/) |
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform with DKMS |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

## ai-maintainer

The `ai_maintainer` tag installs a weekly cron job (Sunday 3 AM) that runs the
[ai-maintainer](https://github.com/andornaut/ai-maintainer) script to merge
dependabot PRs, update dependencies, and fix test/CI failures across
`~/src/github.com/andornaut/`. It only applies to hosts in the `ai_maintainer`
inventory group. The script is symlinked from a local checkout when present,
otherwise downloaded. Configure schedule and behavior via the
`dev_ai_maintainer_*` vars in [defaults/main.yml](./defaults/main.yml).

Run manually: `~/.local/bin/ai-maintainer --dry-run --verbose`.
