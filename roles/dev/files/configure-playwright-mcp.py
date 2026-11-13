#!/usr/bin/python3
import argparse
import fcntl
import json
import os
import re
import stat
import tempfile
import tomllib
from decimal import Decimal, InvalidOperation
from pathlib import Path


def capped_args(cpus, image, record):
    if record is None:
        return [
            "run",
            "-i",
            "--rm",
            "--init",
            "--network=bridge",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            f"--cpus={cpus}",
            image,
            "--isolated",
        ]
    args = record.get("args", [])
    if Path(record.get("command", "")).name != "docker" or not args or args[0] != "run":
        raise ValueError("Playwright registration is not a Docker run command")
    index = next((i for i, value in enumerate(args) if value.startswith("mcr.microsoft.com/playwright/mcp:")), None)
    if index is None:
        raise ValueError("Playwright Docker image is not recognized")
    prefix = []
    limit = Decimal(str(cpus))
    cursor = 0
    while cursor < index:
        value = args[cursor]
        if value == "--cpus" or value.startswith("--cpus="):
            if value == "--cpus":
                cursor += 1
                if cursor >= index:
                    raise ValueError("Docker CPU count is missing")
                value = args[cursor]
            else:
                value = value.split("=", 1)[1]
            try:
                current = Decimal(value)
            except InvalidOperation as error:
                raise ValueError("Docker CPU count is invalid") from error
            if not current.is_finite() or current <= 0:
                raise ValueError("Docker CPU count must be finite and positive")
            limit = min(limit, current)
        elif re.match(r"--cpu-(quota|period)(=|$)", value):
            raise ValueError("Conflicting Docker CPU quota flags require explicit reconciliation")
        else:
            prefix.append(value)
        cursor += 1
    return [*prefix, f"--cpus={limit}", *args[index:]]


def render(harness, cpus, image, original):
    if harness == "claude":
        document = json.loads(original) if original else {}
        servers = document.setdefault("mcpServers", {})
        record = servers.get("playwright")
        args = capped_args(cpus, image, record)
        if record is not None and record.get("args") == args:
            return original
        if record is None:
            record = servers["playwright"] = {"type": "stdio", "command": "/usr/bin/docker"}
        record["args"] = args
        return json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    document = tomllib.loads(original)
    record = document.get("mcp_servers", {}).get("playwright")
    args = capped_args(cpus, image, record)
    if record is not None and record.get("args") == args:
        return original
    literal = json.dumps(args, ensure_ascii=False)
    if record is None:
        result = (
            original.rstrip() + '\n\n[mcp_servers.playwright]\ncommand = "/usr/bin/docker"\nargs = ' + literal + "\n"
        )
        tomllib.loads(result)
        return result
    lines = original.splitlines(keepends=True)
    header = re.compile(r"""^\s*\[\s*mcp_servers\s*\.\s*(?:playwright|"playwright"|'playwright')\s*\]\s*(?:#.*)?$""")
    start = next((i for i, line in enumerate(lines) if header.fullmatch(line.strip())), None)
    if start is None:
        raise ValueError("Unsupported Playwright TOML table layout")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    argument = next((i for i in range(start + 1, end) if re.match(r"\s*args\s*=", lines[i])), None)
    if argument is None:
        raise ValueError("Unsupported Playwright TOML args layout")
    for stop in range(argument + 1, end + 1):
        try:
            parsed = tomllib.loads("".join(lines[argument:stop]))
        except tomllib.TOMLDecodeError:
            continue
        if list(parsed) == ["args"]:
            result = "".join(lines[:argument]) + f"args = {literal}\n" + "".join(lines[stop:])
            tomllib.loads(result)
            return result
    raise ValueError("Unsupported Playwright TOML args literal")


def configure(home, harness, cpus, image, check=False, before_write=lambda: None):
    source = home / (".claude.json" if harness == "claude" else ".codex/config.toml")
    path = source.resolve()
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
    lock = None
    temporary = None
    try:
        if not check:
            lock = os.open(str(path) + ".playwright.lock", os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = path.read_text() if path.exists() else ""
        metadata = path.stat() if path.exists() else None
        fingerprint = metadata
        if metadata and metadata.st_uid != os.getuid():
            raise ValueError("Configuration belongs to another account")
        rendered = render(harness, cpus, image, original)
        if rendered == original:
            return False
        if check:
            return True
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        with os.fdopen(fd, "w") as stream:
            if metadata:
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode) if metadata else 0o600)
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        before_write()
        if (
            source.resolve() != path
            or (path.stat() if path.exists() else None) != fingerprint
            or (path.read_text() if path.exists() else "") != original
        ):
            raise ValueError("Configuration changed concurrently; retry")
        Path(temporary).replace(path)
        temporary = None
        return True
    finally:
        if temporary:
            Path(temporary).unlink()
        if lock is not None:
            os.close(lock)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--harness", choices=["claude", "codex"], required=True)
    parser.add_argument("--cpus", type=int, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.cpus < 1 or not re.fullmatch(r"mcr\.microsoft\.com/playwright/mcp:v[0-9.]+", args.image):
        parser.error("CPU count must be positive and the Playwright image must be version-pinned")
    try:
        changed = configure(args.home, args.harness, args.cpus, args.image, args.check)
    except (OSError, ValueError, TypeError, AttributeError):
        parser.exit(1, "Playwright configuration update failed; configuration contents are withheld\n")
    print(json.dumps({"changed": changed}))


if __name__ == "__main__":
    main()
