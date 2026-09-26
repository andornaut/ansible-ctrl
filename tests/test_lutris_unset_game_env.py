import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

try:
    import yaml
except ImportError:
    yaml = None

SCRIPT = Path(__file__).resolve().parent.parent / "roles/games/files/lutris-unset-game-env.py"


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


@unittest.skipIf(yaml is None, "PyYAML is not installed, and the script imports it")
class UnsetGameEnv(unittest.TestCase):
    def setUp(self):
        self.script = load(SCRIPT)
        config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(config_dir.cleanup)
        self.config_dir = Path(config_dir.name)
        self.games = self.config_dir / "games"
        self.games.mkdir()

    def write(self, name, config):
        path = self.games / f"{name}.yml"
        path.write_text(yaml.safe_dump(config))
        return path

    def run_script(self):
        env = {"LUTRIS_UNSET_ENV_CONFIG": json.dumps({"config_dir": str(self.config_dir), "names": ["DXVK_HUD"]})}
        out = StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            self.script.main()
        return out.getvalue()

    def test_removes_the_name_and_keeps_the_rest(self):
        path = self.write(
            "battlenet",
            {
                "game": {"exe": "Battle.net.exe"},
                "system": {"env": {"DXVK_HUD": "compiler", "STAGING_SHARED_MEMORY": "1"}, "gamescope": True},
                "script": {"system": {"env": {"DXVK_HUD": "compiler"}}},
            },
        )
        self.assertEqual(self.run_script(), f"wrote {path}\n")
        self.assertEqual(
            yaml.safe_load(path.read_text()),
            {
                "game": {"exe": "Battle.net.exe"},
                "system": {"env": {"STAGING_SHARED_MEMORY": "1"}, "gamescope": True},
                "script": {"system": {"env": {"DXVK_HUD": "compiler"}}},
            },
        )

    def test_drops_an_env_left_empty(self):
        path = self.write("a", {"system": {"env": {"DXVK_HUD": "compiler"}, "gamescope": True}})
        self.run_script()
        self.assertEqual(yaml.safe_load(path.read_text()), {"system": {"gamescope": True}})

    def test_converged_files_are_left_alone(self):
        unset = self.write("a", {"system": {"env": {"OTHER": "1"}}})
        no_system = self.write("b", {"game": {"exe": "x"}})
        empty = self.games / "c.yml"
        empty.write_text("")
        before = {path: path.stat().st_mtime_ns for path in (unset, no_system, empty)}
        self.assertEqual(self.run_script(), "")
        self.assertEqual({path: path.stat().st_mtime_ns for path in before}, before)


if __name__ == "__main__":
    unittest.main()
