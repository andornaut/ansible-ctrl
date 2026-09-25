import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vars_plugins"))

import faramir_env
from ansible.errors import AnsibleParserError


class Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.basedir = directory.name
        # The parsed names are cached per directory for the life of the process.
        cache = mock.patch.dict(faramir_env._names_by_basedir, clear=True)
        cache.start()
        self.addCleanup(cache.stop)

    def write(self, content, encoding="utf-8"):
        Path(self.basedir, faramir_env.ENV_FILE).write_bytes(content.encode(encoding))


class DeclaredNames(Base):
    def test_both_line_forms_in_file_order(self):
        self.write("B_TOKEN=faramir://site/b\nA_TOKEN\n")
        self.assertEqual(faramir_env.declared_names(self.basedir), ["B_TOKEN", "A_TOKEN"])

    def test_blank_lines_and_whole_line_comments_are_skipped(self):
        self.write("# heading\n\n   \n  # indented\nNAME\n")
        self.assertEqual(faramir_env.declared_names(self.basedir), ["NAME"])

    def test_a_comment_after_whitespace_is_cut(self):
        self.write("ONE # note\nTWO=faramir://two\t# note\n")
        self.assertEqual(faramir_env.declared_names(self.basedir), ["ONE", "TWO"])

    def test_whitespace_around_the_name_is_ignored(self):
        self.write("  NAME = faramir://name\n")
        self.assertEqual(faramir_env.declared_names(self.basedir), ["NAME"])

    def test_a_file_declaring_nothing_is_not_an_error(self):
        self.write("# nothing\n")
        self.assertEqual(faramir_env.declared_names(self.basedir), [])

    def test_an_unusable_name_names_the_file_and_line(self):
        for line in ("1ST", "has-dash", "NAME#glued", "export NAME=faramir://x", "=faramir://x"):
            with self.subTest(line=line):
                faramir_env._names_by_basedir.clear()
                self.write(f"GOOD\n{line}\n")
                with self.assertRaisesRegex(AnsibleParserError, r"faramir\.env:2: .* not a usable"):
                    faramir_env.declared_names(self.basedir)

    def test_a_missing_file_stops_the_run_naming_it(self):
        with self.assertRaisesRegex(AnsibleParserError, r"faramir\.env is not there"):
            faramir_env.declared_names(self.basedir)

    def test_a_file_that_is_not_text_stops_the_run(self):
        self.write("NAME\n\xff\n", encoding="latin-1")
        with self.assertRaisesRegex(AnsibleParserError, "could not be read"):
            faramir_env.declared_names(self.basedir)

    def test_read_once_per_directory(self):
        self.write("FIRST\n")
        faramir_env.declared_names(self.basedir)
        self.write("SECOND\n")
        self.assertEqual(faramir_env.declared_names(self.basedir), ["FIRST"])


class GetVars(Base):
    def get_vars(self, environ):
        loader = mock.Mock()
        loader.get_basedir.return_value = self.basedir
        with mock.patch.dict(faramir_env.environ, environ, clear=True):
            return faramir_env.VarsModule().get_vars(loader, self.basedir, [])

    def test_set_values_are_returned_and_counted(self):
        self.write("A\nB=faramir://b\n")
        self.assertEqual(self.get_vars({"A": "a", "B": "b"}), {"A": "a", "B": "b", "secrets_injected": 2})

    def test_unset_and_empty_values_are_absent(self):
        self.write("SET\nEMPTY\nUNSET\n")
        self.assertEqual(self.get_vars({"SET": "x", "EMPTY": ""}), {"SET": "x", "secrets_injected": 1})

    def test_an_undeclared_variable_is_not_returned(self):
        self.write("DECLARED\n")
        self.assertEqual(self.get_vars({"OTHER": "x"}), {"secrets_injected": 0})


if __name__ == "__main__":
    unittest.main()
