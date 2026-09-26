import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "roles/faramir/files/prune-agent-rules.py"


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


prune = load(SCRIPT)

# A settings document in the shape faramir merges into, holding every class of character the
# two encoders could spell differently: HTML-significant ones, a shell redirection in an allow
# entry, accents, CJK, an astral character, the two line separators, quote, backslash, slash
# and control characters.
SAMPLE = (
    '{"permissions": {"deny": ["Read(//srv/a<b>&c/**)"], "allow": ["Bash(make lint 2>&1)"],'
    ' "defaultMode": "default"},'
    ' "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",'
    ' "command": "faramir hook --agent claude"}]}]},'
    ' "env": {"TEXT": "caf\\u00e9 \\u4e2d\\u6587 \\ud83d\\ude00 \\u2028\\u2029 \\"q\\" \\\\ /'
    ' \\t\\n\\b\\f\\u0001\\u007f"},'
    ' "empty": {}, "none": [], "flags": [true, false, null], "count": 1234567890123, "ratio": 0.25}'
)

# SAMPLE as Go's encoding/json writes it with SetEscapeHTML(false) and SetIndent("", "  "),
# the encoder faramir's MergeJSON runs. Produced by `go run` over SAMPLE, not written by hand.
GOLDEN = (
    "{\n"
    '  "count": 1234567890123,\n'
    '  "empty": {},\n'
    '  "env": {\n'
    '    "TEXT": "caf\xe9 \u4e2d\u6587 \U0001f600 \\u2028\\u2029 \\"q\\" \\\\ / \\t\\n\\b\\f\\u0001\x7f"\n'
    "  },\n"
    '  "flags": [\n'
    "    true,\n"
    "    false,\n"
    "    null\n"
    "  ],\n"
    '  "hooks": {\n'
    '    "PreToolUse": [\n'
    "      {\n"
    '        "hooks": [\n'
    "          {\n"
    '            "command": "faramir hook --agent claude",\n'
    '            "type": "command"\n'
    "          }\n"
    "        ],\n"
    '        "matcher": "Bash"\n'
    "      }\n"
    "    ]\n"
    "  },\n"
    '  "none": [],\n'
    '  "permissions": {\n'
    '    "allow": [\n'
    '      "Bash(make lint 2>&1)"\n'
    "    ],\n"
    '    "defaultMode": "default",\n'
    '    "deny": [\n'
    '      "Read(//srv/a<b>&c/**)"\n'
    "    ]\n"
    "  },\n"
    '  "ratio": 0.25\n'
    "}\n"
)


# Floats in each notation Go picks between, at both of its thresholds, integral ones that Go
# writes with no fractional part, and negative zero, in arrays and in nested objects.
FLOATS = (
    '{"deny": ["Read(/x)"], "floats": [0.5, 1.0, 100.0, 1e20, 1e21, 1.5e-6, 1e-7, 2.5e-07,'
    ' 123456789.125, -0.0, -3.0], "nested": {"ratio": -2.5e-07, "rows": [{"big": 1e22, "small": 1e-5}]}}'
)

# FLOATS through the same encoder as GOLDEN, decoded into a map. Produced by `go run` over
# FLOATS, not written by hand.
FLOATS_GOLDEN = (
    "{\n"
    '  "deny": [\n'
    '    "Read(/x)"\n'
    "  ],\n"
    '  "floats": [\n'
    "    0.5,\n"
    "    1,\n"
    "    100,\n"
    "    100000000000000000000,\n"
    "    1e+21,\n"
    "    0.0000015,\n"
    "    1e-7,\n"
    "    2.5e-7,\n"
    "    123456789.125,\n"
    "    -0,\n"
    "    -3\n"
    "  ],\n"
    '  "nested": {\n'
    '    "ratio": -2.5e-7,\n'
    '    "rows": [\n'
    "      {\n"
    '        "big": 1e+22,\n'
    '        "small": 0.00001\n'
    "      }\n"
    "    ]\n"
    "  }\n"
    "}\n"
)


class PruneDocument(unittest.TestCase):
    def prune(self, document, keep):
        left_alone = []
        removed = prune.prune_document(document, set(keep), left_alone)
        return removed, left_alone

    def test_drops_only_entries_outside_keep_preserving_order(self):
        document = {"permissions": {"deny": ["c", "a", "stale", "b"], "allow": ["stale"]}}
        removed, left_alone = self.prune(document, ["a", "b", "c"])
        self.assertEqual(removed, ["stale"])
        self.assertEqual(left_alone, [])
        self.assertEqual(document, {"permissions": {"deny": ["c", "a", "b"], "allow": ["stale"]}})

    def test_reaches_deny_lists_nested_in_objects_and_arrays(self):
        document = {
            "deny": ["top", "kept"],
            "profiles": [{"rules": {"deny": ["deep", "kept"]}}, {"deny": []}],
        }
        removed, _ = self.prune(document, ["kept"])
        self.assertEqual(sorted(removed), ["deep", "top"])
        self.assertEqual(document["deny"], ["kept"])
        self.assertEqual(document["profiles"][0]["rules"]["deny"], ["kept"])

    def test_a_list_holding_a_non_string_is_left_whole_and_its_length_reported(self):
        mixed = ["stale", {"pattern": "x"}, 3]
        document = {"deny": mixed, "nested": {"deny": ["stale"]}}
        removed, left_alone = self.prune(document, [])
        self.assertIs(document["deny"], mixed)
        self.assertEqual(mixed, ["stale", {"pattern": "x"}, 3])
        self.assertEqual(left_alone, [3])
        self.assertEqual(removed, ["stale"])
        self.assertEqual(document["nested"]["deny"], [])

    def test_an_object_shaped_deny_is_walked_not_pruned(self):
        document = {"deny": {"Read(/x)": "deny", "inner": {"deny": ["stale"]}}}
        removed, left_alone = self.prune(document, [])
        self.assertEqual(removed, ["stale"])
        self.assertEqual(left_alone, [])
        self.assertIn("Read(/x)", document["deny"])

    def test_a_deny_list_already_inside_keep_is_unchanged(self):
        document = {"deny": ["a"]}
        self.assertEqual(self.prune(document, ["a", "b"]), ([], []))
        self.assertEqual(document, {"deny": ["a"]})


class Serialise(unittest.TestCase):
    def test_matches_go_encoder_byte_for_byte(self):
        self.assertEqual(prune.serialise(json.loads(SAMPLE)).encode(), GOLDEN.encode())

    def test_floats_match_go_encoder_byte_for_byte(self):
        self.assertEqual(prune.serialise(json.loads(FLOATS)).encode(), FLOATS_GOLDEN.encode())

    def test_integers_are_written_as_go_float64s(self):
        # Produced by `go run` through the same encoder, decoded into a map.
        document = json.loads(
            '{"ints": [0, 7, -12, 9007199254740993, 123456789012345678901,'
            ' 100000000000000000000, 1000000000000000000000], "b": true}'
        )
        self.assertEqual(
            prune.serialise(document),
            '{\n  "b": true,\n  "ints": [\n    0,\n    7,\n    -12,\n    9007199254740992,\n'
            "    123456789012345680000,\n    100000000000000000000,\n    1e+21\n  ]\n}\n",
        )

    def test_a_string_spelled_like_a_number_stays_a_string(self):
        self.assertEqual(prune.serialise({"a": 1.0, "b": "1.0"}), '{\n  "a": 1,\n  "b": "1.0"\n}\n')

    def test_non_ascii_is_literal_and_only_the_line_separators_are_escaped(self):
        text = prune.serialise({"k": "caf\u00e9 \u2028 \u2029 <&>"})
        self.assertIn("caf\u00e9", text)
        self.assertIn("\\u2028 \\u2029", text)
        self.assertNotIn("\u2028", text)
        self.assertIn("<&>", text)

    def test_keys_sorted_at_every_depth(self):
        text = prune.serialise({"b": {"z": 1, "a": 2}, "a": 0})
        self.assertEqual(text, '{\n  "a": 0,\n  "b": {\n    "a": 2,\n    "z": 1\n  }\n}\n')

    def test_ends_in_exactly_one_newline(self):
        text = prune.serialise({})
        self.assertEqual(text, "{}\n")


if __name__ == "__main__":
    unittest.main()
