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
| [antigravity](https://us-central1-apt.pkg.dev/projects/antigravity-auto-updater-dev/) | Google auto-updater tool |
| [claude](https://docs.anthropic.com/en/docs/claude-code) | AI coding assistant |
| [codex](https://github.com/openai/codex) | OpenAI Codex CLI |
| [cursor](https://www.cursor.com/) | AI code editor (AppImage) |
| [delta](https://github.com/dandavison/delta) | Syntax-highlighting diff viewer for git |
| [filectrl](https://github.com/andornaut/filectrl) | File manager |
| [gemini](https://github.com/google-gemini/gemini-cli) | Google Gemini CLI |
| [go](https://go.dev/) | Go toolchain |
| javascript | [Node.js](https://nodejs.org/) and [nvm](https://github.com/nvm-sh/nvm) |
| [opencode](https://github.com/opencode-ai/opencode) | OpenCode AI tool |
| [python](https://www.python.org/) | Python 3 with pip, venv, pipenv |
| [ruby](https://www.ruby-lang.org/) | Ruby with [chruby](https://github.com/postmodern/chruby) and [ruby-install](https://github.com/postmodern/ruby-install) |
| [rust](https://www.rust-lang.org/) | Rust toolchain via [rustup](https://rustup.rs/) |
| [virtualbox](https://www.virtualbox.org/) | Virtualization platform with DKMS |
| [vscode](https://code.visualstudio.com/) | Visual Studio Code |

## Variables

See [defaults/main.yml](./defaults/main.yml).
