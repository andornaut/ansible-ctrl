import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "roles/games/files/retroarch-generate-playlists.py"


def load(path):
    """Import a script whose file name is not a module name, writing no bytecode beside it."""
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module


generator = load(SCRIPT)


class TempDir(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def touch(self, relative, content=""):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class ContentLabel(unittest.TestCase):
    def test_longest_extension_wins(self):
        self.assertEqual(generator.content_label("Celeste.p8.png", ["png", "p8.png"]), "Celeste")

    def test_match_is_case_insensitive_and_keeps_the_name_as_written(self):
        self.assertEqual(generator.content_label("Tetris (World).GB", ["gb"]), "Tetris (World)")

    def test_only_a_whole_suffix_after_a_dot_matches(self):
        self.assertIsNone(generator.content_label("Game.xgb", ["gb"]))
        self.assertIsNone(generator.content_label("Game.gb.txt", ["gb"]))


class DiscEntry(TempDir):
    def test_prefers_disc_1_over_sort_order(self):
        for name in ("Game (Bonus Disc).chd", "Game (Disc 2).chd", "Game (Disc 1).chd"):
            self.touch(f"Game/{name}")
        self.assertEqual(
            generator.disc_entry(str(self.root / "Game"), ["chd"]), str(self.root / "Game/Game (Disc 1).chd")
        )

    def test_disc_10_is_not_disc_1(self):
        for name in ("Game (Bonus Disc).chd", "Game (Disc 10).chd", "Game (Disc 2).chd"):
            self.touch(f"Game/{name}")
        self.assertEqual(
            generator.disc_entry(str(self.root / "Game"), ["chd"]), str(self.root / "Game/Game (Bonus Disc).chd")
        )

    def test_falls_back_to_the_first_disc_by_name(self):
        self.touch("Game/b.iso")
        self.touch("Game/a.iso")
        self.assertEqual(generator.disc_entry(str(self.root / "Game"), ["iso"]), str(self.root / "Game/a.iso"))

    def test_ignores_subdirectories_and_other_extensions(self):
        self.touch("Game/readme.txt")
        self.touch("Game/nested/Game (Disc 1).iso")
        self.assertIsNone(generator.disc_entry(str(self.root / "Game"), ["iso"]))


class IsGeneratedPlaylist(TempDir):
    def check(self, content, library="/library"):
        return generator.is_generated_playlist(self.touch("p.lpl", content), library)

    def test_scanned_inside_the_library_is_generated(self):
        self.assertTrue(self.check(json.dumps({"scan_content_dir": "/library/Nintendo - Game Boy"})))
        self.assertTrue(self.check(json.dumps({"scan_content_dir": "/library"}), library="/library/"))

    def test_a_sibling_sharing_the_prefix_is_not(self):
        self.assertFalse(self.check(json.dumps({"scan_content_dir": "/library-old/x"})))

    def test_anything_uncertain_is_kept(self):
        for content in (
            "{not json",
            "[]",
            json.dumps({"items": []}),
            json.dumps({"scan_content_dir": "library/x"}),
            json.dumps({"scan_content_dir": 7}),
        ):
            with self.subTest(content=content):
                self.assertFalse(self.check(content))

    def test_a_missing_file_is_kept(self):
        self.assertFalse(generator.is_generated_playlist(self.root / "absent.lpl", "/library"))


class PrunePlaylists(TempDir):
    def test_removes_only_generated_playlists_of_unlisted_systems(self):
        generated = json.dumps({"scan_content_dir": "/library/x"})
        self.touch("Dropped.lpl", generated)
        self.touch("Listed.lpl", generated)
        self.touch("Handmade.lpl", json.dumps({"items": []}))
        self.touch("notes.txt", generated)
        self.touch("builtin/Nested.lpl", generated)
        (self.root / "Dir.lpl").mkdir()
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            removed = generator.prune_playlists(self.root, "/library", {"Listed": {}})
        self.assertEqual(removed, ["removed Dropped.lpl"])
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            ["Dir.lpl", "Handmade.lpl", "Listed.lpl", "builtin", "notes.txt"],
        )
        self.assertTrue((self.root / "builtin/Nested.lpl").exists())
        self.assertIn("kept Handmade.lpl", stderr.getvalue())


class CorePath(TempDir):
    def test_a_named_core_file_replaces_the_suffix_rule_for_that_core_alone(self):
        self.touch("library/Nintendo - Nintendo 3DS/Game (USA).3ds")
        self.touch("library/Nintendo - Game Boy/Game (USA).zip")
        (self.root / "playlists").mkdir()
        systems = {
            "Nintendo - Nintendo 3DS": {"core": "azahar", "extensions": ["3ds"]},
            "Nintendo - Game Boy": {"core": "gambatte", "extensions": ["zip"]},
        }
        config = {
            "library_dir": str(self.root / "library"),
            "playlist_dir": str(self.root / "playlists"),
            "cores_dir": "/cores",
            "info_dir": str(self.root / "info"),
            "cores": {
                core: {"library_name": core, "valid_extensions": spec["extensions"], "block_extract": False}
                for spec in systems.values()
                for core in [spec["core"]]
            },
            "systems": systems,
            "core_filename_suffix": "_libretro_android.so",
            "core_filenames": {"azahar": "azahar_libretro.so"},
        }
        with (
            mock.patch.dict(os.environ, {"RETROARCH_GENERATOR_CONFIG": json.dumps(config)}),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            generator.main()
        core_paths = {
            system: json.loads((self.root / "playlists" / f"{system}.lpl").read_text())["default_core_path"]
            for system in systems
        }
        self.assertEqual(
            core_paths,
            {
                "Nintendo - Nintendo 3DS": "/cores/azahar_libretro.so",
                "Nintendo - Game Boy": "/cores/gambatte_libretro_android.so",
            },
        )


if __name__ == "__main__":
    unittest.main()
