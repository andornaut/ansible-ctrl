import html
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "roles/games/files/wow-install-addons.py"


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


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def page(releases):
    data = {"component": "Addon/AddonDetails", "props": {"metadata": {"recent_releases": releases}}}
    return f'<html><div id="app" data-page="{html.escape(json.dumps(data))}"></div></html>'


class InstallAddons(unittest.TestCase):
    def setUp(self):
        self.script = load(SCRIPT)
        wow_dir = tempfile.TemporaryDirectory()
        self.addCleanup(wow_dir.cleanup)
        self.wow_dir = Path(wow_dir.name)
        self.responses = {}
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        return self.responses[url]

    def publish(self, slug, releases, payloads):
        self.responses[self.script.PAGE_URL.format(slug=slug)] = page(releases).encode()
        self.responses.update(payloads)

    def run_script(self, flavors, addons):
        env = {"WOW_ADDONS_CONFIG": json.dumps({"wow_dir": str(self.wow_dir), "flavors": flavors, "addons": addons})}
        out = StringIO()
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(self.script, "fetch", self.fetch),
            redirect_stdout(out),
        ):
            self.script.main()
        return out.getvalue()

    def addons(self, version):
        return self.wow_dir / version / "Interface" / "AddOns"

    def test_installs_into_each_present_version_with_a_release(self):
        for version in ("_retail_", "_classic_beta_", "_classic_era_"):
            (self.wow_dir / version).mkdir()
        zip_v1 = archive({"Bag/Bag.toc": "## Version: 1\n"})
        self.publish(
            "bag",
            {
                "retail": {"label": "1", "download_link": "r"},
                "forever": {"label": "1", "download_link": "f"},
                "mop": None,
            },
            {"r": zip_v1, "f": zip_v1},
        )
        out = self.run_script(
            {"_retail_": "retail", "_classic_beta_": "forever", "_classic_era_": "classic", "_classic_": "mop"}, ["bag"]
        )
        self.assertEqual(out.splitlines(), ["bag 1 -> _classic_beta_", "bag 1 -> _retail_"])
        self.assertTrue((self.addons("_retail_") / "Bag/Bag.toc").exists())
        self.assertTrue((self.addons("_classic_beta_") / "Bag/Bag.toc").exists())
        self.assertFalse(self.addons("_classic_era_").exists())
        self.assertFalse((self.wow_dir / "_classic_").exists())
        # One download serves every version sharing a release.
        self.assertEqual(self.fetched.count("r") + self.fetched.count("f"), 1)

    def test_current_release_is_left_alone(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish("bag", {"retail": {"label": "1", "download_link": "r"}}, {"r": archive({"Bag/Bag.toc": ""})})
        self.run_script({"_retail_": "retail"}, ["bag"])
        self.fetched.clear()
        self.assertEqual(self.run_script({"_retail_": "retail"}, ["bag"]), "")
        self.assertNotIn("r", self.fetched)

    def test_new_release_replaces_the_addon_directories(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish(
            "bag",
            {"retail": {"label": "1", "download_link": "r1"}},
            {"r1": archive({"Bag/Bag.toc": "1", "Bag/Old.lua": "", "Bag_Extra/Bag_Extra.toc": ""})},
        )
        self.run_script({"_retail_": "retail"}, ["bag"])
        (self.addons("_retail_") / "Other").mkdir()
        self.publish("bag", {"retail": {"label": "2", "download_link": "r2"}}, {"r2": archive({"Bag/Bag.toc": "2"})})
        self.assertEqual(self.run_script({"_retail_": "retail"}, ["bag"]), "bag 2 -> _retail_\n")
        addons = self.addons("_retail_")
        self.assertEqual((addons / "Bag/Bag.toc").read_text(), "2")
        self.assertFalse((addons / "Bag/Old.lua").exists())
        self.assertFalse((addons / "Bag_Extra").exists())
        self.assertTrue((addons / "Other").is_dir())
        self.assertEqual(json.loads((addons / ".wago-bag.json").read_text()), {"label": "2", "dirs": ["Bag"]})
        self.assertEqual([p.name for p in (self.wow_dir / "_retail_" / "Interface").iterdir()], ["AddOns"])

    def test_missing_directory_reinstalls(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish("bag", {"retail": {"label": "1", "download_link": "r"}}, {"r": archive({"Bag/Bag.toc": ""})})
        self.run_script({"_retail_": "retail"}, ["bag"])
        (self.addons("_retail_") / "Bag/Bag.toc").unlink()
        (self.addons("_retail_") / "Bag").rmdir()
        self.assertEqual(self.run_script({"_retail_": "retail"}, ["bag"]), "bag 1 -> _retail_\n")

    def test_no_version_present_fetches_nothing(self):
        self.assertEqual(self.run_script({"_retail_": "retail"}, ["bag"]), "")
        self.assertEqual(self.fetched, [])

    def test_rejects_a_file_outside_an_addon_directory(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish("bag", {"retail": {"label": "1", "download_link": "r"}}, {"r": archive({"README.txt": ""})})
        with self.assertRaises(ValueError):
            self.run_script({"_retail_": "retail"}, ["bag"])
        self.assertFalse(self.addons("_retail_").joinpath(".wago-bag.json").exists())

    def test_rejects_a_marker_naming_a_path_outside_addons(self):
        (self.wow_dir / "_retail_").mkdir()
        self.addons("_retail_").mkdir(parents=True)
        (self.addons("_retail_") / ".wago-bag.json").write_text(json.dumps({"label": "0", "dirs": [".."]}))
        self.publish("bag", {"retail": {"label": "1", "download_link": "r"}}, {"r": archive({"Bag/Bag.toc": ""})})
        with self.assertRaises(ValueError):
            self.run_script({"_retail_": "retail"}, ["bag"])
        self.assertTrue(self.addons("_retail_").is_dir())

    def test_page_without_page_data_is_an_error(self):
        with self.assertRaises(ValueError):
            self.script.releases("<html></html>")


if __name__ == "__main__":
    unittest.main()
