import contextlib
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "roles/games/files/lutris-launch-game.py"


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


launcher = load(SCRIPT)

APP_ID = "net.lutris.Lutris"
CLIENT = "C:\\Program Files (x86)\\Battle.net\\Battle.net.exe"


class SplitArguments(unittest.TestCase):
    def test_shell_words(self):
        self.assertEqual(
            launcher.split_arguments('--exec="launch WoW" --flag'),
            ["--exec=launch WoW", "--flag"],
        )

    def test_an_open_quote_is_closed_as_lutris_closes_it(self):
        self.assertEqual(launcher.split_arguments('--exec="launch WoW'), ["--exec=launch WoW"])
        self.assertEqual(launcher.split_arguments("--exec='launch WoW"), ["--exec=launch WoW"])
        self.assertEqual(launcher.split_arguments("a \"b 'c"), ["a", "b 'c"])

    def test_empty(self):
        self.assertEqual(launcher.split_arguments(""), [])


@unittest.skipIf(launcher.yaml is None, "PyYAML is not installed, and entry_launch reads nothing without it")
class EntryLaunch(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.home = Path(home.name)
        environ = mock.patch.dict(os.environ, {"HOME": home.name})
        environ.start()
        self.addCleanup(environ.stop)
        self.base = self.home / ".var/app" / APP_ID
        self.prefix = str(self.home / "Games/battlenet")
        data = self.base / "data/lutris"
        data.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(data / "pga.db")) as conn, conn:
            conn.execute("create table games (slug text, configpath text)")
            conn.execute("insert into games values ('battlenet', 'battlenet-1'), ('blank', '')")

    def write_config(self, text, under="config/lutris"):
        games = self.base / under / "games"
        games.mkdir(parents=True, exist_ok=True)
        (games / "battlenet-1.yml").write_text(text)

    def launch(self, slug="battlenet", prefix=None):
        return launcher.entry_launch(APP_ID, slug, prefix or (self.prefix, "~/Games/battlenet"))

    def test_an_exe_in_drive_c_is_the_client_on_c(self):
        exe = f"{self.prefix}/drive_c/Program Files (x86)/Battle.net/Battle.net.exe"
        self.write_config(f'game:\n  exe: {exe}\n  args: --exec="launch WoW"\n')
        self.assertEqual(
            self.launch(),
            launcher.Launch(exe, ["--exec=launch WoW"], str(Path(exe).parent), "c:\\program files (x86)\\battle.net\\"),
        )

    def test_the_given_spelling_of_the_prefix_is_matched_too(self):
        exe = f"{self.prefix}/drive_c/Client/client.exe"
        self.write_config(f"game:\n  exe: {exe}\n  args: --exec=x\n")
        launch = self.launch(prefix=("/resolved/elsewhere", self.prefix))
        self.assertEqual(launch.client_dir, "c:\\client\\")

    def test_an_exe_outside_the_prefix_is_on_z(self):
        self.write_config("game:\n  exe: /opt/Client/client.exe\n  args: --exec=x\n")
        self.assertEqual(self.launch().client_dir, "z:\\opt\\client\\")

    def test_falls_back_to_the_data_directory_without_a_config_one(self):
        self.write_config("game:\n  exe: /opt/c.exe\n  args: --exec=x\n", under="data/lutris")
        self.assertEqual(self.launch().exe, "/opt/c.exe")

    def test_nothing_to_hand_off(self):
        for config in (
            "game:\n  exe: relative/c.exe\n  args: --exec=x\n",
            "game:\n  exe: /opt/c.exe\n  args: --other\n",
            "game:\n  exe: /opt/c.exe\n",
            "game: {}\n",
            "{not yaml: [\n",
        ):
            with self.subTest(config=config):
                self.write_config(config)
                self.assertIsNone(self.launch())

    def test_an_unknown_or_unconfigured_slug(self):
        self.write_config("game:\n  exe: /opt/c.exe\n  args: --exec=x\n")
        self.assertIsNone(self.launch(slug="absent"))
        self.assertIsNone(self.launch(slug="blank"))

    def test_no_database(self):
        (self.base / "data/lutris/pga.db").unlink()
        self.assertIsNone(self.launch())


# The processes of an idle Battle.net session by pid: (comm, argv[0], environment).
INFRASTRUCTURE = {
    10: ("wineserver", "/app/proton/bin/wineserver", []),
    11: ("services.exe", "C:\\windows\\system32\\services.exe", []),
    12: ("Agent.exe", "C:\\ProgramData\\Battle.net\\Agent\\Agent.9001\\Agent.exe", []),
    13: ("Battle.net.exe", CLIENT, []),
    14: ("bash", "/usr/bin/bash", []),
}


class SessionState(unittest.TestCase):
    """The prefix's processes, stubbed by pid: (comm, argv[0], environment)."""

    def state(
        self, processes, client_dir="c:\\program files (x86)\\battle.net\\", which="/usr/bin/xwininfo", windows=()
    ):
        def argv0(pid):
            return processes[pid][1].encode() + b"\0--flag\0"

        patches = [
            mock.patch.object(launcher, "prefix_pids", lambda prefix, exclude: list(processes)),
            mock.patch.object(launcher, "comm_of", lambda pid: processes[pid][0]),
            mock.patch.object(launcher, "cmdline_of", argv0),
            mock.patch.object(launcher, "environ_of", lambda pid: processes[pid][2]),
            mock.patch.object(launcher.shutil, "which", lambda name: which),
            mock.patch.object(launcher, "candidate_windows", lambda display: list(windows)),
        ]
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            return launcher.session_state(("/p",), set(), client_dir)

    def test_no_wineserver_is_stopped(self):
        processes = {k: v for k, v in INFRASTRUCTURE.items() if v[0] != "wineserver"}
        self.assertEqual(self.state(processes), "stopped")

    def test_only_wine_services_and_the_client_is_idle(self):
        self.assertEqual(self.state(INFRASTRUCTURE), "idle")

    def test_a_windows_image_elsewhere_is_a_running_game(self):
        processes = {**INFRASTRUCTURE, 20: ("Wow.exe", "C:\\Program Files (x86)\\World of Warcraft\\Wow.exe", [])}
        self.assertEqual(self.state(processes), "running")

    def test_a_directory_sharing_the_client_prefix_is_not_the_client(self):
        processes = {**INFRASTRUCTURE, 20: ("x.exe", "C:\\Program Files (x86)\\Battle.net Games\\x.exe", [])}
        self.assertEqual(self.state(processes), "running")

    def test_without_a_client_dir_the_client_is_a_game(self):
        self.assertEqual(self.state(INFRASTRUCTURE, client_dir=None), "running")

    def test_under_gamescope_a_shown_window_is_running_and_nothing_else_is(self):
        display = [b"WINEPREFIX=/p", b"GAMESCOPE_CHILD_XDISPLAY=:5"]
        processes = {10: ("wineserver", "/app/wineserver", display)}
        viewable = [("0x1", "Game", "800x600", "viewable")]
        self.assertEqual(self.state(processes, windows=viewable), "running")
        self.assertEqual(self.state(processes, windows=[("0x1", "Game", "800x600", "unmapped")]), "stopped")
        self.assertEqual(self.state(processes, which=None, windows=viewable), "stopped")


if __name__ == "__main__":
    unittest.main()
