import copy
import importlib.util
import unittest
from pathlib import Path

HELPER = (
    Path(__file__).resolve().parents[1]
    / "roles/homeautomation/files/homeassistant/marketplace.py"
)
spec = importlib.util.spec_from_file_location("marketplace", HELPER)
marketplace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(marketplace)


def repository(**overrides):
    return {
        "id": "42",
        "full_name": "example/integration",
        "category": "integration",
        "installed": True,
        "installed_version": "1.0.0",
        "available_version": "v1.0.0",
        "pending_upgrade": False,
        **overrides,
    }


class Store:
    def __init__(self, repositories, **info):
        self.repositories = copy.deepcopy(repositories)
        self.info = {
            "stage": "running",
            "warning_accepted": True,
            "github_connected": False,
            **info,
        }
        self.calls = []
        self.fail_install = False

    async def call(self, command, **data):
        self.calls.append((command, data))
        if command == "marketplace/info":
            return copy.deepcopy(self.info)
        if command == "marketplace/repositories/list":
            return copy.deepcopy(self.repositories)
        if command == "marketplace/repository/install":
            if self.fail_install:
                raise marketplace.ReconcileError("Installation refused")
            entry = next(item for item in self.repositories if item["id"] == data["repository"])
            entry.update(
                installed=True,
                installed_version=data.get("version", entry["available_version"]),
                pending_upgrade=False,
            )
            return None
        raise AssertionError(f"Unexpected Marketplace command: {command}")

    @property
    def installs(self):
        return [data for command, data in self.calls if command == "marketplace/repository/install"]


class MarketplaceContracts(unittest.IsolatedAsyncioTestCase):
    async def test_converged_catalog_and_pinned_versions_do_not_write(self):
        for version in ("latest", "v1.0.0"):
            with self.subTest(version=version):
                store = Store([repository()])
                result = await marketplace.reconcile(
                    store,
                    [{"repository": "example/integration", "category": "integration", "version": version}],
                )
                self.assertFalse(result["changed"])
                self.assertEqual(store.installs, [])

    async def test_adoption_and_upgrade_install_once_then_converge(self):
        for initial in ({"installed": False}, {"pending_upgrade": True, "available_version": "v2.0.0"}):
            with self.subTest(initial=initial):
                store = Store([repository(**initial), repository(id="99", full_name="other/keep")])
                desired = [{"repository": "example/integration", "category": "integration"}]
                result = await marketplace.reconcile(store, desired)
                self.assertTrue(result["changed"])
                self.assertTrue(result["restart_required"])
                self.assertEqual(store.installs, [{"repository": "42"}])
                self.assertTrue(store.repositories[1]["installed"])
                result = await marketplace.reconcile(store, desired)
                self.assertFalse(result["changed"])
                self.assertEqual(len(store.installs), 1)

    async def test_check_mode_plans_install_without_mutation(self):
        store = Store([repository(installed=False)])
        result = await marketplace.reconcile(
            store, [{"repository": "example/integration", "category": "integration"}], check=True
        )
        self.assertTrue(result["changed"])
        self.assertEqual(result["planned"][0]["action"], "install")
        self.assertFalse(store.repositories[0]["installed"])
        self.assertEqual(store.installs, [])

    async def test_failed_prerequisites_prevent_all_installations(self):
        cases = (
            ({"warning_accepted": False}, {"repository": "other/keep", "category": "integration"}),
            ({}, {"repository": "missing/custom", "category": "integration"}),
            ({}, {"repository": "other/keep", "category": "plugin"}),
        )
        for info, blocked in cases:
            with self.subTest(info=info, blocked=blocked):
                store = Store(
                    [repository(installed=False), repository(id="99", full_name="other/keep")], **info
                )
                with self.assertRaises(marketplace.ReconcileError):
                    await marketplace.reconcile(
                        store,
                        [{"repository": "example/integration", "category": "integration"}, blocked],
                    )
                self.assertEqual(store.installs, [])

    async def test_failed_install_stops_before_later_repositories(self):
        store = Store(
            [repository(installed=False), repository(id="99", full_name="other/later", installed=False)]
        )
        store.fail_install = True
        with self.assertRaises(marketplace.ReconcileError):
            await marketplace.reconcile(
                store,
                [
                    {"repository": "example/integration", "category": "integration"},
                    {"repository": "other/later", "category": "integration"},
                ],
            )
        self.assertEqual(store.installs, [{"repository": "42"}])
        self.assertFalse(store.repositories[1]["installed"])
