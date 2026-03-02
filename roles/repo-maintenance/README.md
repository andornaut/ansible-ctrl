# repo-maintenance

Automated GitHub repository maintenance with AI-powered decision making.

## Usage

```bash
make repo-maintenance
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

This role symlinks to the standalone [github-maintainer](https://github.com/andornaut/github-maintainer) project.

Clone the repository:

```bash
git clone https://github.com/andornaut/github-maintainer.git ~/src/github.com/andornaut/github-maintainer
```

## Manual Execution

```bash
# Run with defaults
~/.local/bin/repo-maintenance

# Dry run (preview changes)
~/.local/bin/repo-maintenance --dry-run --verbose

# Help
~/.local/bin/repo-maintenance --help
```

## Scheduling

By default, runs daily at 3:00 AM via cron. Customize schedule with:

```yaml
repo_maintenance_cron_hour: "2"
repo_maintenance_cron_weekday: "0"  # Sunday only
```

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
