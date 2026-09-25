import os
import shlex
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

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


class Parsing(unittest.TestCase):
    def test_hosts_in_order_each_once_stopping_at_tasks_and_blank_lines(self):
        self.assertEqual(playbook.pick_hosts(LISTING), ["alpha", "bravo"])

    def test_hosts_of_a_bare_group_listing(self):
        self.assertEqual(playbook.pick_hosts("  hosts (2):\n    a\n    b\n"), ["a", "b"])

    def test_roles_are_the_prefix_of_role_task_lines_only(self):
        self.assertEqual(playbook.pick_roles(LISTING), ["base", "torrent"])

    def test_unreachable_reads_only_the_first_line_of_each_result(self):
        self.assertEqual(playbook.pick_unreachable(PROBE), ["bravo", "charlie"])


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
    def test_only_secret_playbooks_read_the_store(self):
        self.assertEqual(playbook.secrets_route("msmtp", {}, False, True), "sops")
        self.assertEqual(playbook.secrets_route("desktop", {}, False, False), "none")

    def test_skipped_by_the_knob(self):
        self.assertEqual(playbook.secrets_route("msmtp", {"SECRETS": "none"}, False, False), "none")

    def test_an_unreadable_store_re_enters_as_root_and_root_is_refused(self):
        self.assertEqual(playbook.secrets_route("msmtp", {}, False, False), "sudo")
        self.assertEqual(playbook.secrets_route("msmtp", {}, True, False), "refuse")
        self.assertEqual(playbook.secrets_route("msmtp", {}, True, True), "sops")

    ARGS = ("-e", "a=it's b", "--limit", "x,y", "$HOME", "`id`")

    def test_sops_runs_the_playbook_itself_in_its_own_process(self):
        argv = ["ansible-playbook", "msmtp.yml", *self.ARGS]
        command = playbook.sops_command("/home/op/store.sops.yml", argv)
        self.assertEqual(command[:4], ["sops", "exec-env", "--same-process", "/home/op/store.sops.yml"])
        self.assertEqual(len(command), 5)
        self.assertEqual(shlex.split(command[4]), ["exec", *argv])

    def test_sudo_re_entry_names_each_set_knob_and_carried_name_again(self):
        env = {"SECRETS": "", "ASK_PASS": "1", "PREFLIGHT": "none", "OTHER": "x", "PLAYBOOK_LISTED_HOSTS": "a,b"}
        self.assertEqual(
            playbook.sudo_command(env, "msmtp", list(self.ARGS)),
            [
                "sudo",
                "env",
                "ASK_PASS=1",
                "PREFLIGHT=none",
                "PLAYBOOK_LISTED_HOSTS=a,b",
                str(playbook.SCRIPT),
                "run",
                "msmtp",
                *self.ARGS,
            ],
        )

    def test_sudo_re_entry_without_knobs(self):
        self.assertEqual(playbook.sudo_command({}, "msmtp", []), ["sudo", str(playbook.SCRIPT), "run", "msmtp"])

    def test_carried_hosts_are_read_under_root_only(self):
        env = {"PLAYBOOK_LISTED_HOSTS": "a,b"}
        self.assertEqual(playbook.carried_hosts(env, True), ["a", "b"])
        self.assertIsNone(playbook.carried_hosts(env, False))
        self.assertIsNone(playbook.carried_hosts({"PLAYBOOK_LISTED_HOSTS": " "}, True))


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


class ExitStatus(unittest.TestCase):
    def test_a_drop_turns_success_into_its_own_status(self):
        self.assertEqual(playbook.exit_status(0, True), playbook.DROPPED_EXIT)
        self.assertEqual(playbook.exit_status(0, False), 0)

    def test_the_playbook_failure_outranks_a_drop(self):
        self.assertEqual(playbook.exit_status(2, True), 2)

    def test_a_signal_reads_as_a_shell_reports_it(self):
        self.assertEqual(playbook.exit_status(-2, False), 130)


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class RunOrder(unittest.TestCase):
    """The listing comes before the sudo re-entry, and root does not list again."""

    def run_playbook(self, name, *, root, env=(), readable=False, listing=None, probe=""):
        self.said = []
        with (
            mock.patch.object(playbook, "say", side_effect=self.said.append),
            mock.patch.dict(playbook.os.environ, dict(env), clear=True),
            mock.patch.object(playbook, "is_root", return_value=root),
            mock.patch.object(playbook, "operator", return_value="op"),
            mock.patch.object(playbook, "home_of", return_value="/nonexistent"),
            mock.patch.object(playbook.os, "access", return_value=readable),
            mock.patch.object(playbook, "capture_all", return_value=listing or completed(stdout=LISTING)) as listed,
            mock.patch.object(playbook, "capture", return_value=probe),
            mock.patch.object(playbook.os, "execvp", side_effect=SystemExit("re-entered")) as execvp,
            mock.patch.object(playbook, "run_child", return_value=0) as child,
        ):
            try:
                status = playbook.run(name, [])
            except SystemExit:
                status = None
        return status, listed, execvp, child

    def test_a_failed_listing_is_refused_before_the_re_entry(self):
        status, _, execvp, _ = self.run_playbook("msmtp", root=False, listing=completed(4, stderr="ERROR!"))
        self.assertEqual(status, 1)
        execvp.assert_not_called()

    def test_the_re_entry_carries_the_listed_hosts(self):
        status, listed, execvp, _ = self.run_playbook("msmtp", root=False)
        self.assertIsNone(status)
        listed.assert_called_once()
        self.assertIn("PLAYBOOK_LISTED_HOSTS=alpha,bravo", execvp.call_args.args[1])

    def test_root_behind_the_re_entry_lists_nothing(self):
        env = {"PLAYBOOK_LISTED_HOSTS": "alpha", "PREFLIGHT": "none"}
        status, listed, _, child = self.run_playbook("msmtp", root=True, env=env, readable=True)
        self.assertEqual(status, 0)
        listed.assert_not_called()
        self.assertEqual(child.call_args.args[0][:3], ["sops", "exec-env", "--same-process"])

    def test_a_drop_exits_non_zero_after_a_successful_playbook(self):
        status, _, _, child = self.run_playbook("desktop", root=False, probe="bravo | UNREACHABLE! => {}\n")
        self.assertEqual(status, playbook.DROPPED_EXIT)
        self.assertEqual(child.call_args.args[0][-2:], ["--limit", "alpha"])
        self.assertEqual(sum("dropped bravo" in line for line in self.said), 2)


class RunChild(unittest.TestCase):
    def test_a_sigterm_while_the_child_starts_is_passed_on(self):
        child = mock.Mock()
        child.wait.return_value = 0

        def start(*_args, **_kwargs):
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        with mock.patch.object(playbook.subprocess, "Popen", side_effect=start):
            self.assertEqual(playbook.run_child(["true"]), 0)
        child.send_signal.assert_called_once_with(signal.SIGTERM)


class Listing(unittest.TestCase):
    def test_a_failed_listing_stops_the_run_naming_why(self):
        message = playbook.listing_refusal("base", 4, "ERROR! faramir.env is not there\n", [])
        self.assertIn("ERROR! faramir.env is not there", message)
        self.assertIn("base.yml failed", message)

    def test_no_host_stops_the_run(self):
        self.assertIn("No host matched base.yml", playbook.listing_refusal("base", 0, "", []))

    def test_hosts_listed_runs(self):
        self.assertIsNone(playbook.listing_refusal("base", 0, "[WARNING]: something\n", ["a"]))


class Consistency(unittest.TestCase):
    def test_secret_playbooks_are_the_ones_that_require_credentials(self):
        requiring = {p.stem for p in playbook.REPO.glob("*.yml") if "tasks/require_credentials.yml" in p.read_text()}
        self.assertEqual(playbook.SECRET_PLAYBOOKS, requiring)

    def test_every_delegation_is_one_the_grep_sees(self):
        for path in playbook.REPO.glob("roles/**/*.yml"):
            for line in path.read_bytes().splitlines():
                if line.lstrip().startswith((b"delegate_to:", b"local_action:")):
                    with self.subTest(path=str(path), line=line):
                        self.assertTrue(playbook.DELEGATES_LOCALLY.search(line))

    def test_the_makefile_has_a_target_for_every_playbook(self):
        makefile = (playbook.REPO / "Makefile").read_text().replace("\\\n", " ")
        declared = next(line for line in makefile.splitlines() if line.startswith("PLAYBOOKS :="))
        playbooks = {p.stem for p in playbook.REPO.glob("*.yml") if p.name != "requirements.yml"}
        self.assertEqual(set(declared.split(":=", 1)[1].split()), playbooks)


if __name__ == "__main__":
    unittest.main()
