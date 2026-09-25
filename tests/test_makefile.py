import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make(*args, dry_run=True, env=None):
    return subprocess.run(
        ["make", "--no-print-directory", *(["-n"] if dry_run else []), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def playbook_line(result):
    return next(line for line in result.stdout.splitlines() if line.startswith("bin/playbook.py"))


class Forwarding(unittest.TestCase):
    def test_each_forwarded_word_is_quoted_for_the_shell(self):
        result = make("base", "--", "--limit", "all:&dev", "--extra-vars", '{"a":1}')
        self.assertEqual(
            playbook_line(result),
            """bin/playbook.py run base '--limit' 'all:&dev' '--extra-vars' '{"a":1}'""",
        )

    def test_a_glob_is_not_expanded(self):
        self.assertEqual(
            playbook_line(make("base", "--", "--limit", "web*")), "bin/playbook.py run base '--limit' 'web*'"
        )

    def test_a_single_quote_survives(self):
        self.assertEqual(
            playbook_line(make("base", "--", "--limit", "it's")), "bin/playbook.py run base '--limit' 'it'\\''s'"
        )

    def test_a_command_line_args_is_shell_parsed_as_documented(self):
        result = make("faramir", "ARGS=--extra-vars k=v")
        self.assertEqual(playbook_line(result), "bin/playbook.py run faramir --extra-vars k=v")


class Refusal(unittest.TestCase):
    def test_a_stray_assignment_beside_a_command_line_args_is_refused(self):
        # Run for real, the refusal being bin/playbook.py's. The requirements stamp is taken as
        # current, and ansible is a stub that fails, so a run the refusal misses applies nothing.
        with tempfile.TemporaryDirectory() as stubs:
            for name in ("ansible", "ansible-playbook"):
                stub = Path(stubs, name)
                stub.write_text("#!/bin/sh\nexit 1\n")
                stub.chmod(0o755)
            env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"}
            result = make(
                "-o", ".ansible/.requirements", "desktop", "ARGS=--tags x", "ASK_PAS=1", dry_run=False, env=env
            )
        self.assertNotEqual(result.returncode, 0)
        # ASK_PAS=1 alone: none of ARGS's words is taken for an assignment.
        self.assertIn("variable assignments rather than forwarding them:\n  ASK_PAS=1\n", result.stderr)


class Goals(unittest.TestCase):
    def test_a_mistyped_target_fails(self):
        # Run for real: -n prints the failing recipe without running it. It only echoes.
        result = make("desktpo", dry_run=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no target 'desktpo'", result.stderr)

    def test_a_forwarded_word_naming_a_target_does_not_run_it(self):
        for word in ("clean", "lint", "help"):
            with self.subTest(word=word):
                result = make("desktop", "--", "--tags", word)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("rm -rf", result.stdout)
                self.assertNotIn("tests/lint.sh", result.stdout)
                # help's lines still print under -n, as `:` no-ops rather than echo.
                self.assertNotIn('echo "Available targets', result.stdout)

    def test_the_first_goal_still_runs(self):
        self.assertIn("rm -rf", make("clean").stdout)
        self.assertIn("tests/lint.sh", make("lint").stdout)
        self.assertIn("Available targets", make("help", dry_run=False).stdout)
        self.assertIn("Available targets", make(dry_run=False).stdout)


class Clean(unittest.TestCase):
    def clean(self, hooks_path):
        # Run for real in a scratch repository holding only what the Makefile reads.
        with tempfile.TemporaryDirectory() as tree:
            Path(tree, "bin").mkdir()
            for name in ("Makefile", "bin/playbook.py"):
                target = Path(tree, name)
                target.write_bytes((ROOT / name).read_bytes())
                target.chmod((ROOT / name).stat().st_mode)
            Path(tree, "node_modules").mkdir()
            subprocess.run(["git", "init", "-q", tree], check=True)
            subprocess.run(["git", "-C", tree, "config", "core.hooksPath", hooks_path], check=True)
            result = subprocess.run(
                ["make", "--no-print-directory", "-C", tree, "clean"], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(Path(tree, "node_modules").exists())
            return subprocess.run(
                ["git", "-C", tree, "config", "--local", "--get", "core.hooksPath"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()

    def test_the_husky_hooks_path_goes_with_node_modules(self):
        self.assertEqual(self.clean(".husky/_"), "")

    def test_another_hooks_path_is_kept(self):
        self.assertEqual(self.clean("hooks"), "hooks")


if __name__ == "__main__":
    unittest.main()
