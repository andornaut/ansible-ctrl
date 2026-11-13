import importlib.util
import io
import json
import stat
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "roles/dev/files/configure-playwright-mcp.py"
spec = importlib.util.spec_from_file_location("playwright_mcp", SCRIPT)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
IMAGE = "mcr.microsoft.com/playwright/mcp:v0.0.83"
ARGS = [
    "run",
    "-i",
    "--rm",
    "--init",
    "--network",
    "fixture-network",
    "--cap-drop=ALL",
    "--security-opt",
    "no-new-privileges:true",
    IMAGE,
    "--isolated",
    "--cpus=server-option",
]


class PlaywrightMcpTest(unittest.TestCase):
    def test_existing_options_and_server_arguments_are_preserved(self):
        for cpus in [[], ["--cpus", "8"], ["--cpus=8", "--cpus", "6"]]:
            with self.subTest(cpus=cpus):
                record = {"command": "/usr/bin/docker", "args": ARGS[:1] + cpus + ARGS[1:]}
                result = mcp.capped_args(4, IMAGE, record)
                self.assertEqual(result, [*ARGS[:9], "--cpus=4", *ARGS[9:]])
                self.assertEqual(mcp.capped_args(4, IMAGE, {**record, "args": result}), result)

    def test_conflicting_quota_or_non_docker_transport_fails_closed(self):
        for record in [
            {"command": "node", "args": ARGS},
            {"command": "docker", "args": ["run", "--cpu-quota=800000", IMAGE]},
        ]:
            with self.subTest(record=record), self.assertRaises(ValueError):
                mcp.capped_args(4, IMAGE, record)

    def test_stricter_fractional_caps_are_retained_and_bad_values_fail_closed(self):
        for value in ["2", "0.5", "4"]:
            record = {"command": "docker", "args": ["run", "--cpus", value, IMAGE]}
            self.assertIn(f"--cpus={value}", mcp.capped_args(4, IMAGE, record))
        for values in [
            ["--cpus"],
            ["--cpus", "--init"],
            ["--cpus="],
            ["--cpus=NaN"],
            ["--cpus=Infinity"],
            ["--cpus=-1"],
            ["--cpus=0"],
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                mcp.capped_args(4, IMAGE, {"command": "docker", "args": ["run", *values, IMAGE]})

    def test_inline_toml_table_without_playwright_fails_without_invalid_output(self):
        with self.assertRaises(tomllib.TOMLDecodeError):
            mcp.render("codex", 4, IMAGE, 'mcp_servers = { faramir = { command = "faramir" } }\n')

    def test_claude_preserves_unrelated_records_and_playwright_fields(self):
        original = {
            "unrelated": {"enabled": True},
            "mcpServers": {
                "faramir": {"command": "faramir", "args": ["mcp"]},
                "playwright": {"command": "/usr/bin/docker", "args": ARGS, "env": {"FIXTURE": "reference"}},
            },
        }
        result = json.loads(mcp.render("claude", 4, IMAGE, json.dumps(original)))
        expected = json.loads(json.dumps(original))
        expected["mcpServers"]["playwright"]["args"] = [*ARGS[:9], "--cpus=4", *ARGS[9:]]
        self.assertEqual(result, expected)

    def test_codex_preserves_unrelated_bytes_and_nested_fields(self):
        before = '# unrelated comment\nmodel = "fixture-model"\n[mcp_servers.faramir]\ncommand = "faramir"\n'
        after = '[mcp_servers.playwright.env]\nFIXTURE = "reference"\n'
        for header in ["[mcp_servers.playwright]", '[mcp_servers."playwright"]', "[mcp_servers.'playwright']"]:
            with self.subTest(header=header):
                original = (
                    before
                    + header
                    + '\ncommand = "docker"\nargs = [\n'
                    + ",\n".join(json.dumps(a) for a in ARGS)
                    + "\n]\nenabled = true\n"
                    + after
                )
                result = mcp.render("codex", 4, IMAGE, original)
                self.assertTrue(result.startswith(before))
                self.assertTrue(result.endswith("enabled = true\n" + after))
                record = tomllib.loads(result)["mcp_servers"]["playwright"]
                self.assertEqual(record["args"], [*ARGS[:9], "--cpus=4", *ARGS[9:]])
                self.assertEqual(mcp.render("codex", 4, IMAGE, result), result)

    def test_missing_records_receive_same_pinned_defaults(self):
        claude = json.loads(mcp.render("claude", 3, IMAGE, ""))["mcpServers"]["playwright"]
        codex = tomllib.loads(mcp.render("codex", 3, IMAGE, ""))["mcp_servers"]["playwright"]
        self.assertEqual(claude["command"], codex["command"])
        self.assertEqual(claude["args"], codex["args"])
        self.assertIn("--cpus=3", claude["args"])
        self.assertIn(IMAGE, claude["args"])

    def test_atomic_update_preserves_symlink_mode_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = home / "managed.json"
            target.write_text("{}\n")
            target.chmod(0o640)
            (home / ".claude.json").symlink_to(target)
            self.assertTrue(mcp.configure(home, "claude", 4, IMAGE))
            self.assertTrue((home / ".claude.json").is_symlink())
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
            fingerprint = (target.read_bytes(), target.stat().st_mtime_ns)
            self.assertFalse(mcp.configure(home, "claude", 4, IMAGE))
            self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), fingerprint)

    def test_check_mode_creates_no_directory_lock_or_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "absent"
            self.assertTrue(mcp.configure(home, "codex", 4, IMAGE, check=True))
            self.assertFalse(home.exists())

    def test_concurrent_writer_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / ".claude.json"
            config.write_text("{}\n")

            def concurrent_write():
                config.write_text('{"concurrent": true}\n')

            with self.assertRaisesRegex(ValueError, "concurrently"):
                mcp.configure(home, "claude", 4, IMAGE, before_write=concurrent_write)
            self.assertEqual(json.loads(config.read_text()), {"concurrent": True})
            self.assertEqual(sorted(p.name for p in home.iterdir()), [".claude.json", ".claude.json.playwright.lock"])

    def test_failed_cli_withholds_configuration_and_exception_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".claude.json").write_text("fixture-invalid-document")
            arguments = [
                str(SCRIPT),
                "--home",
                str(home),
                "--harness",
                "claude",
                "--cpus",
                "4",
                "--image",
                IMAGE,
            ]
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch.object(sys, "argv", arguments),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                self.assertRaises(SystemExit) as result,
            ):
                mcp.main()
            self.assertEqual(result.exception.code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("fixture-invalid-document", stderr.getvalue())
            self.assertIn("contents are withheld", stderr.getvalue())

    def test_concurrent_metadata_or_same_bytes_replacement_is_not_overwritten(self):
        for mutation in ["chmod", "replace", "symlink"]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                config = home / ".claude.json"
                config.write_text("{}\n")

                def concurrent_write(mutation=mutation, home=home, config=config):
                    if mutation == "chmod":
                        config.chmod(0o640)
                    elif mutation == "replace":
                        replacement = home / "replacement"
                        replacement.write_text("{}\n")
                        replacement.replace(config)
                    else:
                        config.unlink()
                        target = home / "new-target"
                        target.write_text("{}\n")
                        config.symlink_to(target)

                with self.assertRaisesRegex(ValueError, "concurrently"):
                    mcp.configure(home, "claude", 4, IMAGE, before_write=concurrent_write)
                self.assertEqual(config.read_text(), "{}\n")


if __name__ == "__main__":
    unittest.main()
