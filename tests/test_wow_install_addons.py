import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "roles/games/files/wow-install-addons.py"

RETAIL, CLASSIC_ERA, FOREVER = 517, 67408, 88568


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


def entry(file_id, type_ids, release_type=1):
    return {"id": file_id, "displayName": str(file_id), "releaseType": release_type, "gameVersionTypeIds": type_ids}


class InstallAddons(unittest.TestCase):
    def setUp(self):
        self.script = load(SCRIPT)
        wow_dir = tempfile.TemporaryDirectory()
        self.addCleanup(wow_dir.cleanup)
        self.wow_dir = Path(wow_dir.name)
        self.listings = {}
        self.payloads = {}
        self.fetched = []
        self.downloaded = []

    def fetch_json(self, url):
        self.fetched.append(url)
        return self.listings[url]

    def download(self, directory, url):
        self.downloaded.append(url)
        path = Path(directory) / f"{len(self.downloaded)}.zip"
        path.write_bytes(self.payloads[url])
        return path

    def listing_url(self, project, page):
        return self.script.FILES_URL.format(project=project, page=page, size=self.script.PAGE_SIZE)

    def download_url(self, project, file_id):
        return self.script.DOWNLOAD_URL.format(project=project, file=file_id)

    def publish(self, project, files, payloads):
        """Serve files, newest first, as the project's listing pages, and each payload by file ID."""
        size = self.script.PAGE_SIZE
        pages = [files[i : i + size] for i in range(0, len(files), size)] or [[]]
        for index, chunk in enumerate(pages):
            pagination = {"index": index, "pageSize": size, "totalCount": len(files)}
            self.listings[self.listing_url(project, index)] = {"data": chunk, "pagination": pagination}
        for file_id, payload in payloads.items():
            self.payloads[self.download_url(project, file_id)] = payload

    def run_script(self, flavors, addons):
        config = {"wow_dir": str(self.wow_dir), "flavors": flavors, "addons": addons}
        out = StringIO()
        with (
            mock.patch.dict(os.environ, {"WOW_ADDONS_CONFIG": json.dumps(config)}),
            mock.patch.object(self.script, "fetch_json", self.fetch_json),
            mock.patch.object(self.script, "download", self.download),
            redirect_stdout(out),
        ):
            self.script.main()
        return out.getvalue()

    def addons(self, version):
        return self.wow_dir / version / "Interface" / "AddOns"

    def bag(self, flavors=None):
        return self.run_script(flavors or {"_retail_": RETAIL}, [{"name": "bag", "curseforge_id": 1}])

    def assert_no_scratch_left(self):
        self.assertEqual([p.name for p in self.wow_dir.iterdir() if p.name.startswith(".")], [])

    def test_installs_into_each_present_version_with_a_release(self):
        for version in ("_retail_", "_forever_", "_classic_era_"):
            (self.wow_dir / version).mkdir()
        self.publish(1, [entry(10, [RETAIL, FOREVER])], {10: archive({"Bag/Bag.toc": "## Version: 1\n"})})
        out = self.bag({"_retail_": RETAIL, "_forever_": FOREVER, "_classic_era_": CLASSIC_ERA, "_classic_": 79434})
        self.assertEqual(out.splitlines(), ["bag 10 -> _forever_", "bag 10 -> _retail_"])
        self.assertTrue((self.addons("_retail_") / "Bag/Bag.toc").exists())
        self.assertTrue((self.addons("_forever_") / "Bag/Bag.toc").exists())
        self.assertFalse(self.addons("_classic_era_").exists())
        self.assertFalse((self.wow_dir / "_classic_").exists())
        # One download serves every version sharing a file.
        self.assertEqual(self.downloaded, [self.download_url(1, 10)])
        self.assert_no_scratch_left()

    def test_picks_the_newest_release_per_version(self):
        (self.wow_dir / "_retail_").mkdir()
        (self.wow_dir / "_forever_").mkdir()
        files = [entry(13, [RETAIL], release_type=2), entry(12, [RETAIL]), entry(11, [FOREVER]), entry(10, [RETAIL])]
        self.publish(1, files, {12: archive({"Bag/Bag.toc": "12"}), 11: archive({"Bag/Bag.toc": "11"})})
        self.bag({"_retail_": RETAIL, "_forever_": FOREVER})
        self.assertEqual((self.addons("_retail_") / "Bag/Bag.toc").read_text(), "12")
        self.assertEqual((self.addons("_forever_") / "Bag/Bag.toc").read_text(), "11")

    def test_pages_until_every_version_has_a_release(self):
        self.script.PAGE_SIZE = 2
        (self.wow_dir / "_retail_").mkdir()
        (self.wow_dir / "_forever_").mkdir()
        files = [entry(15, [RETAIL]), entry(14, [RETAIL]), entry(13, [FOREVER]), entry(12, [RETAIL]), entry(11, [])]
        self.publish(1, files, {15: archive({"Bag/Bag.toc": ""}), 13: archive({"Bag/Bag.toc": ""})})
        self.bag({"_retail_": RETAIL, "_forever_": FOREVER})
        self.assertTrue((self.addons("_forever_") / "Bag/Bag.toc").exists())
        self.assertEqual(self.fetched, [self.listing_url(1, 0), self.listing_url(1, 1)])

    def test_stops_paging_at_the_end_of_the_listing(self):
        self.script.PAGE_SIZE = 2
        (self.wow_dir / "_retail_").mkdir()
        (self.wow_dir / "_forever_").mkdir()
        files = [entry(12, [RETAIL]), entry(11, [RETAIL]), entry(10, [RETAIL])]
        self.publish(1, files, {12: archive({"B/B.toc": ""})})
        self.assertEqual(self.bag({"_retail_": RETAIL, "_forever_": FOREVER}), "bag 12 -> _retail_\n")
        self.assertEqual(self.fetched, [self.listing_url(1, 0), self.listing_url(1, 1)])

    def test_current_release_is_left_alone(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish(1, [entry(10, [RETAIL])], {10: archive({"Bag/Bag.toc": ""})})
        self.bag()
        self.downloaded.clear()
        self.assertEqual(self.bag(), "")
        self.assertEqual(self.downloaded, [])

    def test_new_release_replaces_the_addon_directories(self):
        (self.wow_dir / "_retail_").mkdir()
        files = {"Bag/Bag.toc": "1", "Bag/Old.lua": "", "Bag_Extra/Bag_Extra.toc": ""}
        self.publish(1, [entry(10, [RETAIL])], {10: archive(files)})
        self.bag()
        (self.addons("_retail_") / "Other").mkdir()
        self.publish(1, [entry(11, [RETAIL]), entry(10, [RETAIL])], {11: archive({"Bag/Bag.toc": "2"})})
        self.assertEqual(self.bag(), "bag 11 -> _retail_\n")
        addons = self.addons("_retail_")
        self.assertEqual((addons / "Bag/Bag.toc").read_text(), "2")
        self.assertFalse((addons / "Bag/Old.lua").exists())
        self.assertFalse((addons / "Bag_Extra").exists())
        self.assertTrue((addons / "Other").is_dir())
        marker = json.loads((addons / ".curseforge-bag.json").read_text())
        self.assertEqual(marker, {"file": 11, "name": "11", "dirs": ["Bag"]})
        self.assertEqual([p.name for p in (self.wow_dir / "_retail_" / "Interface").iterdir()], ["AddOns"])
        self.assert_no_scratch_left()

    def test_replaces_the_directories_a_wago_marker_names(self):
        addons = self.addons("_retail_")
        (addons / "Bag").mkdir(parents=True)
        (addons / "Bag_Old").mkdir()
        (addons / ".wago-bag.json").write_text(json.dumps({"label": "9", "dirs": ["Bag", "Bag_Old"]}))
        self.publish(1, [entry(10, [RETAIL])], {10: archive({"Bag/Bag.toc": ""})})
        self.assertEqual(self.bag(), "bag 10 -> _retail_\n")
        self.assertTrue((addons / "Bag/Bag.toc").exists())
        self.assertFalse((addons / "Bag_Old").exists())
        self.assertFalse((addons / ".wago-bag.json").exists())
        self.assertTrue((addons / ".curseforge-bag.json").exists())

    def test_replaces_unmarked_directories_the_archive_names(self):
        addons = self.addons("_retail_")
        (addons / "Bag").mkdir(parents=True)
        (addons / "Bag/Stale.lua").write_text("")
        self.publish(1, [entry(10, [RETAIL])], {10: archive({"Bag/Bag.toc": ""})})
        self.bag()
        self.assertEqual(sorted(p.name for p in (addons / "Bag").iterdir()), ["Bag.toc"])

    def test_missing_directory_reinstalls(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish(1, [entry(10, [RETAIL])], {10: archive({"Bag/Bag.toc": ""})})
        self.bag()
        (self.addons("_retail_") / "Bag/Bag.toc").unlink()
        (self.addons("_retail_") / "Bag").rmdir()
        self.assertEqual(self.bag(), "bag 10 -> _retail_\n")

    def test_no_version_present_fetches_nothing(self):
        self.assertEqual(self.bag(), "")
        self.assertEqual(self.fetched, [])

    def test_no_release_for_any_present_version_downloads_nothing(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish(1, [entry(10, [FOREVER]), entry(9, [RETAIL], release_type=2)], {})
        self.assertEqual(self.bag(), "")
        self.assertEqual(self.downloaded, [])

    def test_rejects_a_file_outside_an_addon_directory(self):
        (self.wow_dir / "_retail_").mkdir()
        self.publish(1, [entry(10, [RETAIL])], {10: archive({"README.txt": ""})})
        with self.assertRaises(ValueError):
            self.bag()
        self.assertFalse(self.addons("_retail_").joinpath(".curseforge-bag.json").exists())
        self.assert_no_scratch_left()

    def test_rejects_a_marker_naming_a_path_outside_addons(self):
        self.addons("_retail_").mkdir(parents=True)
        (self.addons("_retail_") / ".curseforge-bag.json").write_text(json.dumps({"file": 9, "dirs": [".."]}))
        self.publish(1, [entry(10, [RETAIL])], {10: archive({"Bag/Bag.toc": ""})})
        with self.assertRaises(ValueError):
            self.bag()
        self.assertTrue(self.addons("_retail_").is_dir())

    def test_rejects_an_addon_name_that_is_not_a_plain_file_name(self):
        (self.wow_dir / "_retail_").mkdir()
        with self.assertRaises(ValueError):
            self.run_script({"_retail_": RETAIL}, [{"name": "../bag", "curseforge_id": 1}])
        self.assertEqual(self.fetched, [])


class Fetch(unittest.TestCase):
    def setUp(self):
        self.script = load(SCRIPT)

    def test_refuses_a_redirect_to_a_non_https_url_without_naming_it(self):
        handler = self.script.HttpsOnlyRedirect()
        request = urllib.request.Request("https://www.curseforge.com/")
        with self.assertRaises(ValueError) as raised:
            handler.redirect_request(request, None, 302, "Found", {}, "http://cdn.example/a.zip?key=secret")
        self.assertNotIn("secret", str(raised.exception))

    def test_follows_a_redirect_to_an_https_url(self):
        handler = self.script.HttpsOnlyRedirect()
        request = urllib.request.Request("https://www.curseforge.com/")
        redirected = handler.redirect_request(request, None, 302, "Found", {}, "https://cdn.example/a.zip")
        self.assertEqual(redirected.full_url, "https://cdn.example/a.zip")

    def test_refuses_a_non_https_url(self):
        with self.assertRaises(ValueError):
            self.script.open_https("http://www.curseforge.com/")

    def test_download_streams_into_the_directory(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        with mock.patch.object(self.script, "open_https", return_value=io.BytesIO(b"payload")):
            path = self.script.download(directory.name, "https://www.curseforge.com/x")
        self.assertEqual(path.parent, Path(directory.name))
        self.assertEqual(path.read_bytes(), b"payload")


if __name__ == "__main__":
    unittest.main()
