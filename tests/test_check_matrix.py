import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_matrix

ROOT = Path(__file__).resolve().parent.parent

ALL = [e["name"] for e in check_matrix.MATRIX]


def names(changed):
    return [e["name"] for e in check_matrix.select(changed)]


class Select(unittest.TestCase):
    def test_no_base_runs_everything(self):
        self.assertEqual(names(None), ALL)
        self.assertIsNone(check_matrix.changed_files("0" * 40, "HEAD"))
        self.assertIsNone(check_matrix.changed_files("", "HEAD"))

    def test_a_rename_reaches_the_role_it_left(self):
        with mock.patch.object(check_matrix.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            check_matrix.changed_files("a", "b")
        self.assertIn("--no-renames", run.call_args.args[0])

    def test_a_shared_path_runs_everything(self):
        self.assertEqual(names(["roles/base/tasks/require_tools.yml"]), ALL)
        self.assertEqual(names(["tasks/require_credentials.yml"]), ALL)

    def test_a_role_runs_only_its_entries(self):
        self.assertEqual(names(["roles/games/tasks/main.yml"]), ["games"])
        self.assertEqual(names(["roles/letsencrypt_nginx/README.md"]), ["webservers"])
        self.assertEqual(names(["roles/niri/vars/main.yml"]), ["desktop niri"])

    def test_desktop_runs_every_desktop_entry(self):
        self.assertEqual(names(["desktop.yml"]), ["desktop gnome", "desktop niri", "desktop bspwm"])

    def test_the_tiling_prepare_reaches_its_dev_tasks_only(self):
        self.assertEqual(names(["roles/dev/tasks/rust.yml"]), ["desktop niri", "desktop bspwm", "dev"])
        self.assertEqual(names(["roles/dev/tasks/cursor.yml"]), ["dev"])

    def test_the_rest_of_base_runs_base_only(self):
        self.assertEqual(names(["roles/base/tasks/main.yml"]), ["base"])

    def test_nothing_reached(self):
        self.assertEqual(names(["README.md", "roles/router/tasks/main.yml"]), [])

    def test_a_prefix_is_a_directory_not_a_name(self):
        self.assertEqual(names(["roles/devx/tasks/main.yml"]), [])

    def test_paths_are_not_emitted(self):
        self.assertTrue(all("paths" not in e for e in check_matrix.select(None)))


def playbook_roles(text):
    """The roles a playbook applies: its roles: entries and its import_role names."""
    found = set(re.findall(r"import_role:\n\s+name: (\w+)", text))
    for _indent, block in re.findall(r"^( *)roles:\n((?:\1 .*\n|\s*#.*\n)*)", text, re.MULTILINE):
        found.update(re.findall(r"^\s*- (?:role: )?(\w+)\s*$", block, re.MULTILINE))
    return found


class Complete(unittest.TestCase):
    """The matrix names every path a covered playbook reads, so a new one cannot go unchecked."""

    def test_every_base_entry_point_is_shared(self):
        included = set()
        for path in (ROOT / "roles").rglob("*.yml"):
            included.update(re.findall(r"include_tasks: \.\./\.\./base/tasks/(\S+\.yml)", path.read_text()))
        self.assertTrue(included)
        self.assertLessEqual({f"roles/base/tasks/{f}" for f in included}, set(check_matrix.SHARED))

    def test_every_playbook_is_covered_or_listed(self):
        playbooks = {p.stem for p in ROOT.glob("*.yml")} - {"requirements"}
        covered = {e["playbook"] for e in check_matrix.MATRIX}
        self.assertEqual(playbooks, covered | set(check_matrix.NOT_COVERED))
        self.assertFalse(covered & set(check_matrix.NOT_COVERED))

    def test_every_role_a_covered_playbook_applies_is_in_its_paths(self):
        for playbook in {e["playbook"] for e in check_matrix.MATRIX}:
            paths = {p for e in check_matrix.MATRIX if e["playbook"] == playbook for p in e["paths"]}
            self.assertIn(f"{playbook}.yml", paths)
            roles = playbook_roles((ROOT / f"{playbook}.yml").read_text())
            self.assertTrue(roles, playbook)
            for role in roles:
                self.assertIn(f"roles/{role}/", paths, playbook)

    def test_roles_are_read_from_both_spellings(self):
        text = "- hosts: x\n  roles:\n    - a\n    # b\n    - role: c\n      tags: c\n  tags:\n    - d\n"
        self.assertEqual(playbook_roles(text), {"a", "c"})


if __name__ == "__main__":
    unittest.main()
