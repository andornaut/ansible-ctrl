import shlex
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

import playbook

LISTING = """\
playbook: torrent.yml

  play #1 (torrent): Configure torrent host\tTAGS: []
    pattern: ['torrent']
    hosts (2):
      alpha
      bravo
    tasks:
      torrent : Validate torrent_user\tTAGS: [always]
      Install a roleless task\tTAGS: []
      torrent : Copy .rtorrent.rc\tTAGS: []

  play #2 (faramir_controller): Install the controller-side scripts\tTAGS: []
    pattern: ['faramir_controller']
    hosts (1):
      bravo
    tasks:
      base : Require tools\tTAGS: []

  play #3 (nas): Nothing matched\tTAGS: []
    pattern: ['nas']
    hosts (0):

  play #4 (all:!routers): Everything\tTAGS: []
    pattern: ['all:!routers']
    hosts (1):
      alpha
"""

PROBE = """\
alpha | CHANGED | rc=0 >>

bravo | UNREACHABLE! => {
    "changed": false,
    "msg": "other | UNREACHABLE! quoted inside a message"
}
charlie | UNREACHABLE! => {
    "unreachable": true
}
"""


def listing(*plays):
    """A --list-hosts listing of plays given as (pattern, hosts)."""
    blocks = [
        f"  play #{i} ({pattern}): Name\tTAGS: []\n    pattern: {[pattern]!r}\n    hosts ({len(hosts)}):\n"
        + "".join(f"      {h}\n" for h in hosts)
        for i, (pattern, hosts) in enumerate(plays, 1)
    ]
    return "playbook: x.yml\n\n" + "\n".join(blocks)


class Parsing(unittest.TestCase):
    def test_hosts_in_order_each_once_stopping_at_tasks_and_blank_lines(self):
        self.assertEqual(playbook.pick_hosts(LISTING), ["alpha", "bravo"])

    def test_hosts_of_a_bare_group_listing(self):
        self.assertEqual(playbook.pick_hosts("  hosts (2):\n    a\n    b\n"), ["a", "b"])

    def test_roles_are_the_prefix_of_role_task_lines_only(self):
        self.assertEqual(playbook.pick_roles(LISTING), ["base", "torrent"])

    def test_unreachable_reads_only_the_first_line_of_each_result(self):
        self.assertEqual(playbook.pick_unreachable(PROBE), ["bravo", "charlie"])

    def test_plays_carry_their_pattern_and_hosts(self):
        self.assertEqual(
            playbook.parse_plays(LISTING),
            [
                (["torrent"], ["alpha", "bravo"]),
                (["faramir_controller"], ["bravo"]),
                (["nas"], []),
                (["all:!routers"], ["alpha"]),
            ],
        )


class MakeSemantics(unittest.TestCase):
    def test_set_ignores_surrounding_whitespace(self):
        self.assertFalse(playbook.is_set(None))
        self.assertFalse(playbook.is_set(" "))
        self.assertTrue(playbook.is_set("0"))

    def test_none_matches_a_whole_word(self):
        self.assertTrue(playbook.is_none("none"))
        self.assertTrue(playbook.is_none(" none x"))
        self.assertFalse(playbook.is_none("nonee"))
        self.assertFalse(playbook.is_none(None))


class Refusal(unittest.TestCase):
    def test_knobs_are_not_stray(self):
        self.assertIsNone(playbook.refusal("desktop", "SECRETS=none ASK_PASS=1 PREFLIGHT=none", ""))

    def test_other_assignments_are_refused_by_name(self):
        message = playbook.refusal("desktop", "SECRETS=none foo=bar", "")
        self.assertIn("  foo=bar\n", message)
        self.assertNotIn("SECRETS", message)
        self.assertIn("make desktop ARGS='...'", message)

    def test_goal_words_dropped_by_a_command_line_args_are_refused(self):
        message = playbook.refusal("base", "", " --tags x ")
        self.assertIn("make base ARGS='--tags x ...'", message)

    def test_nothing_to_refuse(self):
        self.assertIsNone(playbook.refusal("base", "", "  "))


class Operator(unittest.TestCase):
    def test_broker_answer_first(self):
        env = {"FARAMIR_OPERATOR": "op", "SUDO_USER": "executor"}
        self.assertEqual(playbook.resolve_operator(env, True, "root"), "op")

    def test_sudo_user_only_under_root(self):
        self.assertEqual(playbook.resolve_operator({"SUDO_USER": "op"}, True, "root"), "op")
        self.assertEqual(playbook.resolve_operator({"SUDO_USER": "other"}, False, "me"), "me")

    def test_root_with_neither_is_root(self):
        self.assertEqual(playbook.resolve_operator({"SUDO_USER": ""}, True, "root"), "root")

    def test_broker_key_named_only_where_it_exists(self):
        self.assertEqual(
            playbook.root_defaults("/home/op", lambda _: False),
            {"SOPS_AGE_KEY_FILE": "/home/op/.config/faramir/age.key"},
        )
        self.assertEqual(
            playbook.root_defaults("/home/op", lambda _: True)["ANSIBLE_PRIVATE_KEY_FILE"],
            "/home/op/.config/faramir/id_ed25519",
        )


class Secrets(unittest.TestCase):
    def test_only_secret_playbooks_load(self):
        self.assertTrue(playbook.load_secrets("msmtp", {}))
        self.assertFalse(playbook.load_secrets("desktop", {}))

    def test_skipped_by_the_knob_and_inside_the_re_entry(self):
        self.assertFalse(playbook.load_secrets("msmtp", {"SECRETS": "none"}))
        self.assertFalse(playbook.load_secrets("msmtp", {"SECRETS_LOADED": "1"}))

    ARGS = ("-e", "a=it's b", "--limit", "x,y", "$HOME", "`id`")

    def test_sops_re_entry_quotes_every_argument_into_one_string(self):
        argv = playbook.sops_command("/home/op/store.sops.yml", "msmtp", list(self.ARGS))
        self.assertEqual(argv[:3], ["sops", "exec-env", "/home/op/store.sops.yml"])
        self.assertEqual(len(argv), 4)
        self.assertEqual(shlex.split(argv[3]), ["SECRETS_LOADED=1", str(playbook.SCRIPT), "run", "msmtp", *self.ARGS])

    def test_sudo_re_entry_names_each_set_knob_again(self):
        env = {"SECRETS": "", "ASK_PASS": "1", "PREFLIGHT": "none", "OTHER": "x"}
        self.assertEqual(
            playbook.sudo_command(env, "msmtp", list(self.ARGS)),
            ["sudo", "env", "ASK_PASS=1", "PREFLIGHT=none", str(playbook.SCRIPT), "run", "msmtp", *self.ARGS],
        )

    def test_sudo_re_entry_without_knobs(self):
        self.assertEqual(playbook.sudo_command({}, "msmtp", []), ["sudo", str(playbook.SCRIPT), "run", "msmtp"])


class BecomeFlag(unittest.TestCase):
    def flag(self, *, root=False, forced=None, controller=("ctl",), hosts=("a",), roles=(), delegating=()):
        return playbook.become_flag(
            root, forced, lambda: list(controller), list(hosts), list(roles), lambda r: r in delegating
        )

    def test_root_is_never_prompted(self):
        self.assertEqual(self.flag(root=True, forced="1", hosts=("ctl",)), ())

    def test_forced(self):
        def unasked():
            raise AssertionError

        self.assertEqual(
            playbook.become_flag(False, "1", unasked, [], [], lambda _: False),
            playbook.BECOME_PROMPT,
        )

    def test_blank_ask_pass_does_not_force(self):
        self.assertEqual(self.flag(forced=" "), ())

    def test_controller_in_the_run(self):
        self.assertEqual(self.flag(controller=("ctl", "ctl2"), hosts=("a", "ctl2")), playbook.BECOME_PROMPT)

    def test_empty_controller_group(self):
        self.assertEqual(self.flag(controller=()), playbook.BECOME_PROMPT)

    def test_a_role_delegating_to_localhost(self):
        self.assertEqual(self.flag(roles=("x", "y"), delegating=("y",)), playbook.BECOME_PROMPT)

    def test_a_run_that_avoids_the_controller(self):
        self.assertEqual(self.flag(roles=("x",)), ())

    def test_the_grep_matches_what_a_task_file_says(self):
        self.assertTrue(playbook.DELEGATES_LOCALLY.search(b"  delegate_to:   localhost\n"))
        self.assertFalse(playbook.DELEGATES_LOCALLY.search(b"  delegate_to:\n    localhost\n"))


class Preflight(unittest.TestCase):
    def test_nothing_off_adds_no_limit(self):
        self.assertEqual(playbook.preflight_outcome("base", ["a", "b"], [], False), ([], ""))

    def test_drops_what_is_off(self):
        limit, message = playbook.preflight_outcome("base", ["a", "b", "c"], ["b"], False)
        self.assertEqual(limit, ["--limit", "a,c"])
        self.assertEqual(message, "Preflight: dropped b (no connection)")

    def test_stops_when_nothing_is_left(self):
        limit, message = playbook.preflight_outcome("base", ["a"], ["a"], False)
        self.assertIsNone(limit)
        self.assertIn("nothing left to apply base.yml", message)

    def test_a_root_faramir_run_says_what_a_drop_can_mean(self):
        for root, name, expected in ((True, "faramir", True), (False, "faramir", False), (True, "base", False)):
            with self.subTest(root=root, name=name):
                _, message = playbook.preflight_outcome(name, ["a", "b"], ["b"], root)
                self.assertEqual("make faramir" in message, expected)


class Bootstrap(unittest.TestCase):
    def test_named_groups_only(self):
        self.assertTrue(playbook.names_a_group(["homeautomation"]))
        self.assertTrue(playbook.names_a_group(["dev:homeautomation:webservers"]))
        self.assertFalse(playbook.names_a_group(["all"]))
        self.assertFalse(playbook.names_a_group(["all:!routers"]))
        self.assertFalse(playbook.names_a_group(["*"]))
        self.assertFalse(playbook.names_a_group(["!routers"]))

    def test_selection_and_order(self):
        listings = {
            "base": listing(("all:!routers", ["h"])),
            "docker": listing(("dev:homeautomation", ["h"])),
            "desktop": listing(("desktop", ["h"])),
            "dev": listing(("dev", ["h"])),
            "faramir": listing(("faramir", ["h"]), ("all", ["h"])),
            "msmtp": listing(("all:!routers", ["h"])),
            "torrent": listing(("torrent", []), ("faramir_controller", [])),
            "webservers": listing(("webservers", ["h"])),
            "homeautomation": listing(("homeautomation", ["h"])),
        }
        self.assertEqual(
            playbook.select_bootstrap(listings),
            ["base", "docker", "msmtp", "dev", "desktop", "homeautomation", "webservers"],
        )

    def test_leading_playbooks_skipped_where_they_miss_the_host(self):
        listings = {
            "base": listing(("all:!routers", [])),
            "docker": listing(("dev", [])),
            "router": listing(("routers", ["r"])),
        }
        self.assertEqual(playbook.select_bootstrap(listings), ["router"])

    def test_a_limit_is_required(self):
        for args, expected in (
            (["--limit", "h"], True),
            (["--limit=h"], True),
            (["-l", "h"], True),
            (["-lh"], True),
            (["--tags", "x", "--list-hosts"], False),
            ([], False),
        ):
            with self.subTest(args=args):
                self.assertEqual(playbook.has_limit(args), expected)


if __name__ == "__main__":
    unittest.main()
