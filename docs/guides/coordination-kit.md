# Coordination Kit

Install the standalone Coordination Kit 7.9.0 CLI from the verified release archive.
Run it from the primary checkout. From a linked worktree, pass the primary checkout
path with `--root`. [Installation guide][install]

In the Codex session that will own the maintainer role, start from the primary
checkout.

```sh
primary="$(pwd -P)"
ck() {
    node "$HOME/.local/share/coordination-kit/7.9.0/package/dist/cli.js" --root "$primary" "$@"
}
ck --version
ck init --project ansible-ctrl --role maintainer --review off
ck project register --role maintainer --harness codex --native-id "${CODEX_THREAD_ID:?}"
ck session start
ck skills install lifecycle --harness codex --scope project
ck skills install status --harness codex --scope project
```

Supply `--native-project-id` if Codex reports a separate project ID. Keep the
registry and task history under the ignored `.coordination-kit/` directory.

The bundled skills let you ask to start, resume, or check the status of a task by
description. Codex uses `task find` to look up the task ID.

With `review: off`, the maintainer reviews the candidate and integrates it
through the repository's existing fast-forward workflow on `origin/main`.
Run `make lint` and `make test` before pushing.

Record the user's build approval before starting a task. Commit its
`docs/work/<task-id>.md` work file with the implementation, then record the
checked candidate with `task ready`. Once CI passes for the pushed commit, record
the evidence with `ck task verify TASK_ID --evidence REF`. [Standalone workflow][workflow]

[install]: https://github.com/andornaut/coordination-kit/blob/v7.9.0/docs/getting-started.md#get-the-cli
[workflow]: https://github.com/andornaut/coordination-kit/blob/v7.9.0/docs/standalone.md
