import copy
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HELPER = Path(__file__).resolve().parents[1] / "roles/homeautomation/files/homeassistant/marketplace.py"
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
        self.resources = []

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
        if command == "lovelace/resources/list":
            return copy.deepcopy(self.resources)
        if command == "lovelace/resources/update":
            resource = next(item for item in self.resources if item["id"] == data["resource_id"])
            resource.update(url=data["url"], type=data["res_type"])
            return copy.deepcopy(resource)
        if command == "lovelace/resources/delete":
            self.resources = [item for item in self.resources if item["id"] != data["resource_id"]]
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
                self.assertEqual(
                    store.installs, [{"repository": "42", "version": store.repositories[0]["available_version"]}]
                )
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
                store = Store([repository(installed=False), repository(id="99", full_name="other/keep")], **info)
                with self.assertRaises(marketplace.ReconcileError):
                    await marketplace.reconcile(
                        store,
                        [{"repository": "example/integration", "category": "integration"}, blocked],
                    )
                self.assertEqual(store.installs, [])

    async def test_failed_install_stops_before_later_repositories(self):
        store = Store([repository(installed=False), repository(id="99", full_name="other/later", installed=False)])
        store.fail_install = True
        report = {}
        with self.assertRaises(marketplace.ReconcileError):
            await marketplace.reconcile(
                store,
                [
                    {"repository": "example/integration", "category": "integration"},
                    {"repository": "other/later", "category": "integration"},
                ],
                report=report,
            )
        self.assertEqual(store.installs, [{"repository": "42", "version": "v1.0.0"}])
        self.assertTrue(report["changed"])
        self.assertTrue(report["restart_required"])
        self.assertFalse(store.repositories[1]["installed"])

    async def test_resource_migration_preserves_old_id_and_removes_generated_duplicate(self):
        target = "/local/community/button-card/button-card.js"
        store = Store([repository(full_name="custom-cards/button-card", category="plugin")])
        store.resources = [
            {"id": "old", "url": "/local/button-card.js?v=1", "type": "module"},
            {"id": "generated", "url": target, "type": "module"},
            {"id": "unrelated", "url": "/local/other.js", "type": "module"},
        ]
        desired = [{"repository": "custom-cards/button-card", "category": "plugin"}]
        report = await marketplace.reconcile(store, desired)
        self.assertTrue(report["changed"])
        self.assertEqual(
            store.resources,
            [
                {"id": "old", "url": target, "type": "module"},
                {"id": "unrelated", "url": "/local/other.js", "type": "module"},
            ],
        )
        count = len(store.calls)
        report = await marketplace.reconcile(store, desired)
        self.assertFalse(report["changed"])
        self.assertFalse(any(command.endswith(("/update", "/delete")) for command, _ in store.calls[count:]))


@unittest.skipIf(marketplace.aiohttp is None, "Run transport coverage in the Home Assistant image")
class MarketplaceTransport(unittest.IsolatedAsyncioTestCase):
    async def test_native_catalog_larger_than_default_frame_limit_converges(self):
        from aiohttp import web

        catalog = [repository(description="x" * (5 * 1024 * 1024))]
        response_size = len(json.dumps(catalog).encode())
        self.assertGreater(response_size, 4 * 1024 * 1024)
        commands = []

        async def websocket(request):
            socket = web.WebSocketResponse()
            await socket.prepare(request)
            await socket.send_json({"type": "auth_required", "ha_version": "2026.11.1"})
            authentication = await socket.receive_json()
            self.assertEqual(authentication["type"], "auth")
            await socket.send_json({"type": "auth_ok", "ha_version": "2026.11.1"})
            async for message in socket:
                if message.type != marketplace.aiohttp.WSMsgType.TEXT:
                    continue
                command = message.json()
                commands.append(command["type"])
                if command["type"] == "marketplace/info":
                    result = {"stage": "running", "warning_accepted": True, "github_connected": False}
                elif command["type"] == "marketplace/repositories/list":
                    result = catalog
                else:
                    self.fail(f"Unexpected mutation: {command['type']}")
                await socket.send_json(
                    {"id": command["id"], "type": "result", "success": True, "result": result}
                )
            return socket

        application = web.Application()
        application.router.add_get("/api/websocket", websocket)
        runner = web.AppRunner(application)
        await runner.setup()
        server = web.TCPSite(runner, "127.0.0.1", 0)
        try:
            await server.start()
            port = runner.addresses[0][1]
            args = SimpleNamespace(url=f"http://127.0.0.1:{port}", check=True)
            with mock.patch.dict("os.environ", {"HA_MARKETPLACE_TOKEN": "synthetic-test-auth"}):
                report = await marketplace.run(
                    args, [{"repository": "example/integration", "category": "integration"}], {}
                )
            self.assertFalse(report["changed"])
            self.assertEqual(commands, ["marketplace/info", "marketplace/repositories/list"])
        finally:
            await runner.cleanup()
