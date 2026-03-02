# github-maintainer

Automated GitHub repository maintenance with AI-powered decision making.

## Usage

```bash
make github-maintainer
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

## How It Works

For each repository in `~/src/github.com/{username}/`:

1. Validates it's on the default branch with a clean working directory
2. Pulls latest changes
3. Asks AI to verify open dependabot PRs are legitimate, then merges approved ones
4. Detects dependency files and asks AI which dependencies to update (respects age threshold)
5. Runs tests (auto-detects: npm test, make test, pytest, cargo test, etc.)
6. Commits and pushes if tests pass

## Prerequisites

This role downloads the standalone [github-maintainer](https://github.com/andornaut/github-maintainer) script.

## Manual Execution

```bash
# Run with defaults
~/.local/bin/github-maintainer

# Dry run (preview changes)
~/.local/bin/github-maintainer --dry-run --verbose

# Help
~/.local/bin/github-maintainer --help
```

## Scheduling

By default, runs weekly on Sunday at 3:00 AM via cron. Customize schedule with:

```yaml
github_maintainer_cron_hour: "2"
github_maintainer_cron_weekday: "0"  # Sunday only
```

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
