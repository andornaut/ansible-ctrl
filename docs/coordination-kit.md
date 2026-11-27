# Coordination Kit

Install the standalone Coordination Kit 7.8.0 CLI from the verified release archive.
Run it from the primary checkout. From a linked worktree, pass the primary checkout
path with `--root`. [Installation guide][install]

In the Codex session that will own the maintainer role, start from the primary
checkout.

```sh
primary="$(pwd -P)"
ck() {
    node "$HOME/.local/share/coordination-kit/7.8.0/package/dist/cli.js" --root "$primary" "$@"
}
ck --version
ck init --project ansible-ctrl --role maintainer --review off
ck project register --role maintainer --harness codex --native-id "${CODEX_THREAD_ID:?}"
ck session start
```

Supply `--native-project-id` if Codex reports a separate project ID. Keep the
registry and task history under the ignored `.coordination-kit/` directory.

`review: off` keeps the existing maintainer review and fast-forward workflow on
`origin/main`. Run `make lint` and `make test` before pushing.

Record the user's build approval before starting a task. Commit its
`docs/work/<task-id>.md` work file with the implementation, then record the
checked candidate with `task ready`. Once CI passes for the pushed commit, record
the evidence with `ck task verify TASK_ID --evidence REF`. [Standalone workflow][workflow]

[install]: https://github.com/andornaut/coordination-kit/blob/v7.8.0/docs/getting-started.md#get-the-cli
[workflow]: https://github.com/andornaut/coordination-kit/blob/v7.8.0/docs/standalone.md
