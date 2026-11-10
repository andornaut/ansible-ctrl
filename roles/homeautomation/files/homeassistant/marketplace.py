#!/usr/bin/env python3
"""Reconcile declared repositories through Home Assistant's Marketplace API."""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    import aiohttp
except ModuleNotFoundError:
    aiohttp = None

CATEGORIES = {"integration", "plugin", "theme", "template"}
MAX_MESSAGE_SIZE = 32 * 1024 * 1024
LEGACY_RESOURCES = {
    "dermotduffy/advanced-camera-card": "/local/advanced-camera-card/advanced-camera-card.js",
    "custom-cards/button-card": "/local/button-card.js",
    "thomasloven/lovelace-card-mod": "/local/card-mod.js",
    "nerwyn/custom-card-features": "/local/custom-card-features.min.js",
    "custom-cards/decluttering-card": "/local/decluttering-card.js",
    "thomasloven/lovelace-slider-entity-row": "/local/slider-entity-row.js",
    "skavan/super-text-input": "/local/super-text-input/super-text-input.js",
}


class ReconcileError(Exception):
    """A safe diagnostic which contains no authentication material."""


class Marketplace:
    """Use one authenticated WebSocket connection without logging its messages."""

    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0
        self.command = "authentication"

    async def call(self, command, **data):
        self.command = command
        self.sequence += 1
        request_id = self.sequence
        async with asyncio.timeout(180):
            await self.socket.send_json({"id": request_id, "type": command, **data})
            while True:
                reply = await self.socket.receive_json()
                if not isinstance(reply, dict):
                    raise ReconcileError("Marketplace returned an unexpected WebSocket message")
                if reply.get("type") in {"auth_invalid", "auth_required"}:
                    raise ReconcileError("Marketplace WebSocket authentication expired")
                if reply.get("type") != "result" or reply.get("id") != request_id:
                    continue
                if not reply.get("success"):
                    code = reply.get("error", {}).get("code", "unknown_error")
                    # Server error messages can contain upstream response bodies.
                    safe_code = re.sub(r"[^a-zA-Z0-9_]", "", str(code))[:80]
                    raise ReconcileError(f"{command} failed ({safe_code})")
                return reply.get("result")


def validate_repositories(value):
    """Validate the complete desired set before any request can mutate it."""
    if not isinstance(value, list):
        raise ReconcileError("Repository configuration must be a JSON list")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ReconcileError("Each repository must be an object")
        name = item.get("repository", "")
        category = item.get("category", "")
        version = item.get("version", "latest")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            raise ReconcileError("Repository must be an owner/name pair")
        if category not in CATEGORIES:
            raise ReconcileError(f"Unsupported category for {name}")
        if not isinstance(version, str) or not version.strip():
            raise ReconcileError(f"Missing version for {name}")
        if name.lower() in seen:
            raise ReconcileError(f"Duplicate repository: {name}")
        seen.add(name.lower())
        result.append({"repository": name, "category": category, "version": version})
    return result


def same_version(left, right):
    """Integration manifest versions can omit a release tag's leading v."""
    return str(left).removeprefix("v") == str(right).removeprefix("v")


async def reconcile_resources(client, desired, report, check):
    """Replace only this role's legacy resource URLs after successful installations."""
    plugins = [item for item in desired if item["category"] == "plugin"]
    if not plugins:
        return
    resources = await client.call("lovelace/resources/list")
    for item in plugins:
        legacy = LEGACY_RESOURCES.get(item["repository"].lower())
        if legacy is None:
            continue
        filename = legacy.rsplit("/", 1)[-1]
        repository = item["repository"].split("/", 1)[1]
        target = f"/local/community/{repository}/{filename}"
        matching = [entry for entry in resources if urlsplit(entry["url"]).path == legacy]
        existing = [entry for entry in resources if urlsplit(entry["url"]).path == target]
        for index, resource in enumerate(matching):
            report["planned"].append({"resource": legacy, "action": "replace", "url": target})
            report["changed"] = True
            if check:
                continue
            if index:
                await client.call("lovelace/resources/delete", resource_id=resource["id"])
                continue
            await client.call(
                "lovelace/resources/update",
                resource_id=resource["id"],
                url=target,
                res_type=resource.get("type", "module"),
            )
            for duplicate in existing:
                await client.call("lovelace/resources/delete", resource_id=duplicate["id"])
        if matching and not check:
            readback = await client.call("lovelace/resources/list")
            if any(urlsplit(entry["url"]).path == legacy for entry in readback) or not any(
                urlsplit(entry["url"]).path == target for entry in readback
            ):
                raise ReconcileError(f"Dashboard resource migration was not confirmed for {item['repository']}")


async def reconcile(client, desired, check=False, report=None):
    """Add or install declared content, never remove unrelated repositories."""
    desired = validate_repositories(desired)
    if report is None:
        report = {}
    report.update({"changed": False, "planned": [], "installed": [], "restart_required": False})
    info = await client.call("marketplace/info")
    if info.get("disabled_reason") or info.get("stage") != "running":
        raise ReconcileError("Marketplace is not ready; wait for startup or resolve its repair")
    if info.get("lovelace_mode") == "yaml" and any(item["category"] == "plugin" for item in desired):
        raise ReconcileError("Migrate YAML dashboard resource URLs before enabling Marketplace provisioning")
    if not info.get("warning_accepted"):
        raise ReconcileError(
            "Accept the Marketplace warning in Home Assistant using the account owning "
            "HA_MARKETPLACE_TOKEN, then run provisioning again"
        )
    categories = sorted({item["category"] for item in desired})
    available = await client.call("marketplace/repositories/list", categories=categories)
    repositories = {item["full_name"].lower(): item for item in available}
    # Check all prerequisites before changing any repository.
    for item in desired:
        current = repositories.get(item["repository"].lower())
        if (current is None or current.get("custom")) and not info.get("github_connected"):
            raise ReconcileError(
                f"{item['repository']} needs a Marketplace GitHub connection; connect it in "
                "Home Assistant before provisioning custom repositories"
            )
        if current and current.get("category") != item["category"]:
            raise ReconcileError(f"Marketplace category differs for {item['repository']}")
        if (
            current
            and item["version"] == "latest"
            and not re.fullmatch(r"v?\d+(?:\.\d+){1,3}", str(current.get("available_version", "")))
        ):
            raise ReconcileError(
                f"{item['repository']} does not offer an unambiguous stable release; "
                "disable its Marketplace pre-release selection or declare an explicit version"
            )
    for item in desired:
        name = item["repository"]
        current = repositories.get(name.lower())
        if current is None:
            report["planned"].append({"repository": name, "action": "add"})
            if not check:
                await client.call("marketplace/repositories/add", repository=name, category=item["category"])
                report["changed"] = True
                available = await client.call("marketplace/repositories/list", categories=categories)
                current = next(
                    (entry for entry in available if entry["full_name"].lower() == name.lower()),
                    None,
                )
                if current is None:
                    raise ReconcileError(f"Marketplace did not register {name}")
        version = item["version"]
        target = current.get("available_version") if current and version == "latest" else version
        if current and current.get("installed"):
            if version == "latest" and not current.get("pending_upgrade"):
                continue
            if version != "latest" and same_version(current.get("installed_version"), version):
                continue
        if current and not target:
            raise ReconcileError(f"Marketplace has no available version for {name}")
        report["planned"].append({"repository": name, "action": "install", "version": target})
        if check:
            report["changed"] = True
            report["restart_required"] |= item["category"] == "integration"
            continue
        request = {"repository": str(current["id"]), "version": target}
        # An interrupted or failed install can already have replaced integration files.
        report["changed"] = True
        report["restart_required"] |= item["category"] == "integration"
        await client.call("marketplace/repository/install", **request)
        available = await client.call("marketplace/repositories/list", categories=categories)
        installed = next((entry for entry in available if entry["full_name"].lower() == name.lower()), None)
        if not installed or not installed.get("installed"):
            raise ReconcileError(f"Marketplace did not confirm installation of {name}")
        if not same_version(installed.get("installed_version"), target):
            raise ReconcileError(f"Marketplace installed an unexpected version of {name}")
        report["installed"].append({"repository": name, "version": installed.get("installed_version")})
    await reconcile_resources(client, desired, report, check)
    return report


async def run(args, desired, report):
    token = os.environ.get("HA_MARKETPLACE_TOKEN")
    if not token:
        raise ReconcileError("HA_MARKETPLACE_TOKEN is required; finish administrator onboarding first")
    parsed = urlsplit(args.url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ReconcileError("Use an HTTP(S) URL without embedded authentication")
    endpoint = urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, "/api/websocket", "", ""))
    report["phase"] = "websocket_connect"
    async with (
        aiohttp.ClientSession() as session,
        session.ws_connect(endpoint, max_msg_size=MAX_MESSAGE_SIZE) as socket,
    ):
        report["phase"] = "authentication_handshake"
        hello = await socket.receive_json(timeout=30)
        if hello.get("type") != "auth_required":
            raise ReconcileError("Unexpected Home Assistant authentication handshake")
        version = hello.get("ha_version", "")
        match = re.match(r"^(\d+)\.(\d+)(?:\.|$)", version)
        if not match or (int(match[1]), int(match[2])) < (2026, 11):
            raise ReconcileError("Marketplace provisioning requires Home Assistant 2026.11 or newer")
        await socket.send_json({"type": "auth", "access_token": token})
        if (await socket.receive_json(timeout=30)).get("type") != "auth_ok":
            raise ReconcileError("Home Assistant rejected HA_MARKETPLACE_TOKEN")
        client = Marketplace(socket)
        report["phase"] = "reconciliation"
        try:
            return await reconcile(client, desired, args.check, report)
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError, KeyError, TypeError):
            report["phase"] = client.command
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8123")
    parser.add_argument("--repositories", required=True, help="JSON path, or - for standard input")
    parser.add_argument("--check", action="store_true", help="Plan changes without installing")
    args = parser.parse_args()
    if aiohttp is None:
        print(json.dumps({"failed": True, "changed": False, "error": "Run this helper inside Home Assistant"}))
        return 1
    report = {"changed": False, "planned": [], "installed": [], "restart_required": False}
    try:
        desired = json.loads(sys.stdin.read() if args.repositories == "-" else Path(args.repositories).read_text())
        desired = validate_repositories(desired)
        result = asyncio.run(run(args, desired, report))
    except ReconcileError as error:
        print(json.dumps({**report, "failed": True, "error": str(error)}))
        return 1
    except (aiohttp.ClientError, TimeoutError, OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps(
                {
                    **report,
                    "failed": True,
                    "error": f"Marketplace communication or configuration failed during {report.get('phase', 'configuration')} "
                    f"({type(error).__name__})",
                }
            )
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
