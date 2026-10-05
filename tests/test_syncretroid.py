import contextlib
import importlib.util
import io
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
        # Every write, in order, so a test can check what ran before what.
        self.ops = []
        self.pushed = {}

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
        self.ops.append(("rm", path))

    def mkdirs(self, *paths):
        self.ops.append(("mkdirs", *paths))

    def push(self, local, remote):
        self.ops.append(("push", remote))

    def push_text(self, text, remote):
        self.pushed[remote] = text
        self.ops.append(("push_text", remote))

    def rmdir_empty(self, root):
        self.ops.append(("rmdir_empty", root))

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
    def test_a_listed_playlist_no_longer_generated_is_stale(self):
        previous = "Dropped.lpl\nKept.lpl\n"
        self.assertEqual(sync.stale_playlists(previous, ["Kept.lpl", "New.lpl"]), ["Dropped.lpl"])

    def test_without_a_manifest_nothing_is_stale(self):
        self.assertEqual(sync.stale_playlists(None, ["Kept.lpl"]), [])

    def test_only_bare_lpl_names_count(self):
        previous = "../escape.lpl\nsub/dir.lpl\nnotes.txt\n\nGone.lpl\n"
        self.assertEqual(sync.stale_playlists(previous, []), ["Gone.lpl"])


class OverrideConfigDir(unittest.TestCase):
    CFG = "/data/files/retroarch.cfg"

    def test_the_device_setting_wins(self):
        cfg = 'rgui_config_directory = "/sdcard/RetroArch/config"\n'
        self.assertEqual(sync.override_config_dir(cfg, self.CFG), "/sdcard/RetroArch/config")

    def test_default_or_empty_falls_back_beside_retroarch_cfg(self):
        for value in ('"default"', '""'):
            with self.subTest(value=value):
                cfg = f"rgui_config_directory = {value}\n"
                self.assertEqual(sync.override_config_dir(cfg, self.CFG), "/data/files/config")


class SetAltEmulator(unittest.TestCase):
    BLOCK = "<alternativeEmulator>\n\t<label>Core</label>\n</alternativeEmulator>\n"

    def test_an_existing_block_is_replaced(self):
        existing = (
            '<?xml version="1.0"?>\n<alternativeEmulator>\n\t<label>Old</label>\n</alternativeEmulator>\n<gameList />\n'
        )
        self.assertEqual(sync.set_alt_emulator(existing, "Core"), f'<?xml version="1.0"?>\n{self.BLOCK}<gameList />\n')

    def test_inserted_after_the_declaration(self):
        existing = '<?xml version="1.0"?>\n<gameList />\n'
        self.assertEqual(sync.set_alt_emulator(existing, "Core"), f'<?xml version="1.0"?>\n{self.BLOCK}<gameList />\n')

    def test_a_missing_gamelist_is_created(self):
        self.assertEqual(sync.set_alt_emulator(None, "Core"), f'<?xml version="1.0"?>\n{self.BLOCK}<gameList />\n')

    def test_an_already_pinned_gamelist_comes_back_identical(self):
        existing = sync.set_alt_emulator('<?xml version="1.0"?>\n<gameList />\n', "Core")
        self.assertEqual(sync.set_alt_emulator(existing, "Core"), existing)


class ConfigureEsdeCores(unittest.TestCase):
    def test_only_a_gamelist_that_changes_is_written(self):
        pinned = sync.set_alt_emulator(None, "Core")
        device = FakeDevice(files={"/g/a/gamelist.xml": pinned, "/g/b/gamelist.xml": pinned})
        with contextlib.redirect_stdout(io.StringIO()):
            sync.configure_esde_cores(device, True, "/g", {"a": "Core", "b": "Other"})
        self.assertEqual(list(device.pushed), ["/g/b/gamelist.xml"])


class Decode(unittest.TestCase):
    def test_bytes_that_are_not_utf8_round_trip(self):
        raw = b"caf\xe9\r\n"
        text = sync.decode(raw)
        self.assertTrue(text.endswith("\r\n"))
        self.assertEqual(text.encode("utf-8", "surrogateescape"), raw)


class MirrorTrees(unittest.TestCase):
    """mirror_roms and sync_tree against a real local tree and a FakeDevice listing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = Path(self.tmp.name)

    def write(self, rel, data=b"abc"):
        path = self.lib / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    @staticmethod
    def listing(root, files):
        return "".join(f"{size}\t{root}/{rel}\n" for rel, size in files.items())

    def mirror(self, device):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            sync.mirror_roms(device, True, self.lib, "/sd/ROMS", {"Lib": "dev"})

    def test_device_files_the_library_dropped_are_pruned_and_preserved_ones_kept(self):
        self.write("Lib/keep.rom")
        device = FakeDevice(
            find_output=self.listing("/sd/ROMS/dev", {"keep.rom": 3, "dropped.rom": 3, "systeminfo.txt": 9})
        )
        self.mirror(device)
        self.assertEqual(device.removed, ["/sd/ROMS/dev/dropped.rom"])

    def test_an_unreadable_library_file_stays_on_the_device_and_fails_the_system(self):
        self.write("Lib/keep.rom")
        (self.lib / "Lib/broken.rom").symlink_to(self.lib / "missing")
        device = FakeDevice(find_output=self.listing("/sd/ROMS/dev", {"keep.rom": 3, "broken.rom": 3}))
        with self.assertRaises(SystemExit):
            self.mirror(device)
        self.assertEqual(device.removed, [])

    def test_an_empty_library_directory_prunes_nothing(self):
        (self.lib / "Lib").mkdir()
        device = FakeDevice(find_output=self.listing("/sd/ROMS/dev", {"a.rom": 3}))
        with self.assertRaises(SystemExit):
            self.mirror(device)
        self.assertEqual(device.removed, [])

    def test_emptied_directories_go_before_any_push(self):
        self.write("Lib/Game (USA).game/disc1.bin")
        device = FakeDevice(find_output=self.listing("/sd/ROMS/dev", {"Game (usa).game/disc1.bin": 3}))
        self.mirror(device)
        kinds = [op[0] for op in device.ops]
        self.assertLess(kinds.index("rmdir_empty"), kinds.index("push"))
        self.assertEqual(device.removed, ["/sd/ROMS/dev/Game (usa).game/disc1.bin"])

    def test_only_missing_or_resized_files_are_pushed(self):
        self.write("Lib/same.rom")
        self.write("Lib/resized.rom", b"abcd")
        self.write("Lib/new.rom")
        device = FakeDevice(find_output=self.listing("/sd/ROMS/dev", {"same.rom": 3, "resized.rom": 3}))
        self.mirror(device)
        pushed = [op[1] for op in device.ops if op[0] == "push"]
        self.assertEqual(pushed, ["/sd/ROMS/dev/new.rom", "/sd/ROMS/dev/resized.rom"])

    def sync_tree(self, device, prune):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            sync.sync_tree(device, True, self.lib, "/sd/thumbs", prune)

    def test_sync_tree_without_prune_never_deletes(self):
        self.write("a.png")
        device = FakeDevice(find_output=self.listing("/sd/thumbs", {"a.png": 3, "extra.png": 3}))
        self.sync_tree(device, prune=False)
        self.assertEqual(device.removed, [])
        self.assertNotIn("rmdir_empty", [op[0] for op in device.ops])

    def test_sync_tree_prune_keeps_unreadable_files_and_fails(self):
        self.write("a.png")
        (self.lib / "broken.png").symlink_to(self.lib / "missing")
        device = FakeDevice(find_output=self.listing("/sd/thumbs", {"a.png": 3, "broken.png": 3, "gone.png": 3}))
        with self.assertRaises(SystemExit):
            self.sync_tree(device, prune=True)
        self.assertEqual(device.removed, ["/sd/thumbs/gone.png"])

    def test_sync_tree_refuses_to_prune_against_an_empty_source(self):
        device = FakeDevice(find_output=self.listing("/sd/thumbs", {"a.png": 3}))
        with self.assertRaises(SystemExit):
            self.sync_tree(device, prune=True)
        self.assertEqual(device.removed, [])


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
