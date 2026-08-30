# Covers the branches of identity.py that a run against this repository cannot reach.
#
# A branch only decides anything when the tree holds the shape that triggers it, and this
# tree does not hold most of them: every task is declared, so the read-only set and the
# `uri` dest check never rule on anything; no handler includes a file by a relative name;
# no play declares an account of its own. Break any of those and `tests/lint.sh identity`
# stays green, so they are proven here against a fixture tree instead.
#
# What the repository itself proves is left out: the include-before-scan pass, the depth
# ceiling, the module lookup, a block's declaration reaching its children, and a comment in
# the allowlist all fail the gate today if broken.

import contextlib
import io
import pathlib
import shutil
import tempfile
import textwrap
import unittest

import identity

COPY = """\
  ansible.builtin.copy:
    content: x
    dest: /etc/example
    mode: "0644"
"""

# Whether a task is reported, by what it says about the account and what its module does.
DECLARATION_CASES = (
    ("nothing at all", f"- name: Subject\n{COPY}", True),
    ("become false", f"- name: Subject\n{COPY}  become: false\n", False),
    ("become_user with no become", f"- name: Subject\n{COPY}  become_user: someone\n", False),
    ("a module that only reads", "- name: Subject\n  ansible.builtin.debug:\n    msg: hi\n", False),
    (
        "uri naming dest among the module arguments",
        "- name: Subject\n  ansible.builtin.uri:\n    url: https://example.invalid\n    dest: /etc/example\n",
        True,
    ),
    (
        "uri naming dest in an args block",
        "- name: Subject\n  ansible.builtin.uri:\n    url: https://example.invalid\n  args:\n    dest: /etc/example\n",
        True,
    ),
    (
        "uri naming dest in a free-form string",
        "- name: Subject\n  ansible.builtin.uri: url=https://example.invalid dest=/etc/example\n",
        True,
    ),
    (
        "uri naming no dest",
        "- name: Subject\n  ansible.builtin.uri:\n    url: https://example.invalid\n",
        False,
    ),
)

PLAY = """\
- hosts: all
  {section}:
    - name: Subject
      ansible.builtin.copy:
        content: x
        dest: /etc/example
        mode: "0644"
"""

# Where a task has to sit for the scan to reach it, and what the play around it declares.
LOCATION_CASES = (
    (
        "a role handler",
        {"roles/r/handlers/main.yml": f"- name: Subject\n{COPY}"},
        {"roles/r/handlers/main.yml::Subject"},
    ),
    ("a play's tasks", {"site.yml": PLAY.format(section="tasks")}, {"site.yml::Subject"}),
    ("a play's pre_tasks", {"site.yml": PLAY.format(section="pre_tasks")}, {"site.yml::Subject"}),
    ("a play's post_tasks", {"site.yml": PLAY.format(section="post_tasks")}, {"site.yml::Subject"}),
    (
        "a play that declares an account for its tasks",
        {"site.yml": PLAY.format(section="tasks").replace("- hosts: all\n", "- hosts: all\n  become: true\n")},
        set(),
    ),
)


class IdentityTest(unittest.TestCase):
    """Runs identity.py against a fixture tree rather than against this repository."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.allowlist = self.root / "identity-allowlist.txt"
        self.last = None

    def build(self, files):
        """Replaces the tree, so a case is never read against the one before it."""
        for child in self.root.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text))

    def scan(self, files):
        """A run over a fixture tree, replacing whatever the case before it wrote."""
        self.build(files)
        return identity.Scan(root=self.root, allowlist=self.allowlist)

    def reported(self, files):
        """Every task the scan says leaves its account to the connection."""
        self.last = self.scan(files)
        return {" -> ".join(entry) for entry in identity.collect(self.last)}

    def run_main(self, files, allowlist=""):
        self.last = self.scan(files)
        self.allowlist.write_text(allowlist)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = identity.main(self.last)
        return status, out.getvalue() + err.getvalue()


class WhatCountsAsADeclaredAccount(IdentityTest):
    def test_each_form_of_declaration_and_each_module_that_needs_none(self):
        for label, task, is_reported in DECLARATION_CASES:
            with self.subTest(label):
                expected = {"roles/r/tasks/main.yml::Subject"} if is_reported else set()
                self.assertEqual(expected, self.reported({"roles/r/tasks/main.yml": task}))


class WhereTheScanLooks(IdentityTest):
    def test_each_place_a_task_can_sit(self):
        for label, files, expected in LOCATION_CASES:
            with self.subTest(label):
                self.assertEqual(expected, self.reported(files))


class FollowingAnInclude(IdentityTest):
    def test_a_handler_include_resolves_against_the_roles_tasks_directory(self):
        # A handler's relative include is the one case where the two candidate directories
        # differ: ansible resolves it against tasks/, not against handlers/ beside the file.
        reported = self.reported(
            {
                "roles/r/handlers/main.yml": "- name: Caller\n  ansible.builtin.include_tasks: helper.yml\n",
                "roles/r/tasks/helper.yml": f"- name: Subject\n{COPY}",
            }
        )
        self.assertEqual([], self.last.errors)
        self.assertEqual(
            {"roles/r/handlers/main.yml::Caller -> roles/r/tasks/helper.yml::Subject"},
            reported,
        )


class TheAllowlist(IdentityTest):
    def test_an_allowlisted_task_does_not_fail_the_run(self):
        status, output = self.run_main(
            {"roles/r/tasks/main.yml": f"- name: Subject\n{COPY}"},
            allowlist="# a comment\nroles/r/tasks/main.yml::Subject\n",
        )
        self.assertEqual(0, status, output)

    def test_an_entry_matching_nothing_fails_the_run(self):
        status, output = self.run_main(
            {"roles/r/tasks/main.yml": f"- name: Subject\n{COPY}  become: true\n"},
            allowlist="roles/r/tasks/main.yml::Subject\n",
        )
        self.assertEqual(1, status)
        self.assertIn("stale allowlist entry", output)


class TheExitCode(IdentityTest):
    def test_an_unreadable_include_fails_the_run_with_nothing_else_wrong(self):
        # Every task here is declared, so the run fails on the error alone: a file the scan
        # could not follow means the tasks inside it went unchecked, not that there are none.
        status, output = self.run_main(
            {
                "roles/r/tasks/main.yml": (
                    "- name: Declared\n"
                    "  become: true\n"
                    "  block:\n"
                    "    - name: Computed include\n"
                    '      ansible.builtin.include_tasks: "{{ item }}.yml"\n'
                )
            }
        )
        self.assertEqual(1, status)
        self.assertIn("include target is computed", output)


if __name__ == "__main__":
    unittest.main()
