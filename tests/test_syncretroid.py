import contextlib
import importlib.util
import io
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "roles/games/files/retroid/syncretroid.py"


def load(path):
    """Import a script from a directory that is not a package, writing no bytecode beside it."""
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module


sync = load(SCRIPT)

CONFIG = "/sdcard/RetroArch/config"
DIRS = {"playlists": "/sd/playlists", "roms": "/sd/ROMS"}


class FakeDevice:
    """Answers the reads these functions make from an in-memory file tree, and records writes."""

    def __init__(self, files=None, listing=None, find_output=""):
        self.files = files or {}
        self.listing = listing or {}
        self.find_output = find_output
        self.reads = []
        self.removed = []
        self.rmdirs = []

    def list_dir(self, path):
        return self.listing.get(path, [])

    def pull_text(self, path):
        return self.files.get(path)

    def read(self, command):
        self.reads.append(command)
        if command.startswith("find "):
            return self.find_output
        # The first-lines loop: `for f in <quoted paths>; do ...`. $(head -n 1) keeps a
        # carriage return and drops the newline, as the device shell does.
        quoted = command[len("for f in ") : command.index("; do ")]
        return "".join(f"{path}\t{self.files.get(path, '').split(chr(10))[0]}\n" for path in shlex.split(quoted))

    def rm(self, path):
        self.removed.append(path)

    def rmdir_if_empty(self, path):
        self.rmdirs.append(path)


class MergeCfg(unittest.TestCase):
    def test_rewrites_in_place_drops_and_leaves_the_rest(self):
        existing = '# comment\nvideo_driver = "gl"\nstale_key = "1"\nunmanaged = "x"\n'
        merged = sync.merge_cfg(existing, {"video_driver": "vulkan"}, {"stale_key"})
        self.assertEqual(merged, '# comment\nvideo_driver = "vulkan"\nunmanaged = "x"\n')

    def test_a_loosely_spaced_managed_line_is_normalised(self):
        self.assertEqual(
            sync.merge_cfg("  menu_driver=rgui\n", {"menu_driver": "ozone"}, set()), 'menu_driver = "ozone"\n'
        )

    def test_new_keys_appended_in_managed_order_after_one_blank_line(self):
        merged = sync.merge_cfg('a = "1"\n', {"z": "2", "b": "3"}, set())
        self.assertEqual(merged, 'a = "1"\n\nz = "2"\nb = "3"\n')

    def test_no_second_blank_line_when_the_file_already_ends_in_one(self):
        self.assertEqual(sync.merge_cfg('a = "1"\n\n', {"b": "2"}, set()), 'a = "1"\n\nb = "2"\n')

    def test_empty_or_missing_file_gets_only_the_managed_keys(self):
        for existing in ("", None):
            self.assertEqual(sync.merge_cfg(existing, {"b": "2"}, set()), 'b = "2"\n')

    def test_a_key_both_managed_and_dropped_is_dropped_and_appended(self):
        self.assertEqual(sync.merge_cfg('k = "old"\n', {"k": "new"}, {"k"}), 'k = "new"\n')


class StalePlaylists(unittest.TestCase):
    def stale(self, files, systems=()):
        listing = {DIRS["playlists"]: [name.rsplit("/", 1)[-1] for name in files]}
        device = FakeDevice(files=files, listing=listing)
        return sync.stale_playlists(device, DIRS, set(systems))

    @staticmethod
    def playlist(scanned):
        return json.dumps({"scan_content_dir": scanned})

    def test_only_a_dropped_system_scanned_inside_the_rom_dir_is_stale(self):
        files = {
            "/sd/playlists/Dropped.lpl": self.playlist("/sd/ROMS/dropped"),
            "/sd/playlists/Root.lpl": self.playlist("/sd/ROMS"),
            "/sd/playlists/Kept.lpl": self.playlist("/sd/ROMS/kept"),
            "/sd/playlists/Sibling.lpl": self.playlist("/sd/ROMS_BACKUP/x"),
            "/sd/playlists/Handmade.lpl": json.dumps({"items": []}),
            "/sd/playlists/Garbled.lpl": "{not json",
            "/sd/playlists/notes.txt": self.playlist("/sd/ROMS/x"),
        }
        self.assertEqual(self.stale(files, systems={"Kept"}), ["Dropped.lpl", "Root.lpl"])

    def test_a_playlist_of_another_shape_is_skipped(self):
        files = {
            "/sd/playlists/Array.lpl": json.dumps(["/sd/ROMS/x"]),
            "/sd/playlists/Number.lpl": json.dumps({"scan_content_dir": 3}),
        }
        self.assertEqual(self.stale(files), [])

    def test_a_playlist_gone_between_listing_and_read_is_skipped(self):
        device = FakeDevice(listing={"/sd/playlists": ["Gone.lpl"]})
        self.assertEqual(sync.stale_playlists(device, DIRS, set()), [])


class DeviceFirstLines(unittest.TestCase):
    def test_maps_every_path_to_its_first_line(self):
        files = {
            f"{CONFIG}/A/A.cfg": "# Ansible managed\nx = 1\n",
            f"{CONFIG}/B/it's.opt": "",
            f"{CONFIG}/C/C.slangp": "first\r\nsecond\r\n",
        }
        device = FakeDevice(files=files)
        lines = sync.device_first_lines(device, list(files))
        self.assertEqual(
            lines,
            {f"{CONFIG}/A/A.cfg": "# Ansible managed", f"{CONFIG}/B/it's.opt": "", f"{CONFIG}/C/C.slangp": "first\r"},
        )
        self.assertEqual(len(device.reads), 1)

    def test_batches_stay_under_the_byte_bound_and_cover_every_path_in_order(self):
        paths = [f"{CONFIG}/Core{index}/Core{index}.cfg" for index in range(10)]
        device = FakeDevice(files=dict.fromkeys(paths, "x"))
        # Three quoted paths and their two separating spaces come to one byte over.
        bound = 3 * len(sync.shq(paths[0])) + 1
        with mock.patch.object(sync, "FIRST_LINES_BATCH_BYTES", bound):
            lines = sync.device_first_lines(device, paths)
        self.assertEqual(list(lines), paths)
        self.assertEqual(len(device.reads), 5)
        for command in device.reads:
            quoted = command[len("for f in ") : command.index("; do ")]
            self.assertLessEqual(len(quoted), bound)

    def test_no_paths_reads_nothing(self):
        device = FakeDevice()
        self.assertEqual(sync.device_first_lines(device, []), {})
        self.assertEqual(device.reads, [])

    def test_a_short_read_exits(self):
        device = FakeDevice()
        device.read = lambda _command: "/a\tx\n"
        with self.assertRaises(SystemExit):
            sync.device_first_lines(device, ["/a", "/b"])

    def test_a_row_for_another_path_exits(self):
        device = FakeDevice()
        device.read = lambda _command: "/b\t# Ansible managed\n/a\tx\n"
        with self.assertRaises(SystemExit):
            sync.device_first_lines(device, ["/a", "/b"])

    def test_a_path_that_only_prefixes_the_row_exits(self):
        device = FakeDevice()
        device.read = lambda _command: "/a.cfg.bak\tx\n"
        with self.assertRaises(SystemExit):
            sync.device_first_lines(device, ["/a.cfg"])


class PruneOverrides(unittest.TestCase):
    def setUp(self):
        stage = tempfile.TemporaryDirectory()
        self.addCleanup(stage.cleanup)
        self.stage = Path(stage.name)
        (self.stage / "Staged").mkdir()
        (self.stage / "Staged" / "Staged.cfg").write_text("# Ansible managed\n")

    def run_prune(self, files, online=True, config_dir=CONFIG):
        device = FakeDevice(files=files, find_output="".join(f"{path}\n" for path in files))
        with contextlib.redirect_stdout(io.StringIO()):
            sync.prune_overrides(device, online, config_dir, str(self.stage))
        return device

    def test_removes_only_unstaged_files_whose_first_line_is_the_header(self):
        files = {
            f"{CONFIG}/Staged/Staged.cfg": "# Ansible managed\n",
            f"{CONFIG}/Dropped/Dropped.opt": "# Ansible managed\nx = 1\n",
            f"{CONFIG}/Crlf/Crlf.slangp": "# Ansible managed\r\nshaders = 1\r\n",
            f"{CONFIG}/Saved/Game.cfg": "video_driver = gl\n",
            f"{CONFIG}/Later/Later.cfg": "x = 1\n# Ansible managed\n",
            f"{CONFIG}/Spaced/Spaced.cfg": " # Ansible managed\n",
        }
        device = self.run_prune(files)
        self.assertEqual(device.removed, [f"{CONFIG}/Crlf/Crlf.slangp", f"{CONFIG}/Dropped/Dropped.opt"])
        self.assertEqual(device.rmdirs, [f"{CONFIG}/Crlf", f"{CONFIG}/Dropped"])

    def test_staged_files_are_never_read(self):
        device = self.run_prune({f"{CONFIG}/Staged/Staged.cfg": "# Ansible managed\n"})
        self.assertEqual(device.removed, [])
        self.assertEqual(len(device.reads), 1)

    def test_a_trailing_slash_on_the_config_dir_is_the_same_dir(self):
        device = self.run_prune({f"{CONFIG}/Staged/Staged.cfg": "# Ansible managed\n"}, config_dir=CONFIG + "/")
        self.assertEqual(device.removed, [])

    def test_a_listed_path_outside_the_config_dir_is_ignored(self):
        device = self.run_prune({"/elsewhere/X/X.cfg": "# Ansible managed\n"})
        self.assertEqual(device.removed, [])

    def test_offline_plans_nothing(self):
        device = self.run_prune({f"{CONFIG}/Dropped/Dropped.cfg": "# Ansible managed\n"}, online=False)
        self.assertEqual((device.reads, device.removed), ([], []))


if __name__ == "__main__":
    unittest.main()
