import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_matrix

ALL = [e["name"] for e in check_matrix.MATRIX]


def names(changed):
    return [e["name"] for e in check_matrix.select(changed)]


class Select(unittest.TestCase):
    def test_no_base_runs_everything(self):
        self.assertEqual(names(None), ALL)
        self.assertIsNone(check_matrix.changed_files("0" * 40, "HEAD"))
        self.assertIsNone(check_matrix.changed_files("", "HEAD"))

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


if __name__ == "__main__":
    unittest.main()
