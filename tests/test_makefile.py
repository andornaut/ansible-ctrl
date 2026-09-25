import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make(*args, dry_run=True):
    return subprocess.run(
        ["make", "--no-print-directory", *(["-n"] if dry_run else []), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
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


if __name__ == "__main__":
    unittest.main()
