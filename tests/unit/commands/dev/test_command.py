from unittest import TestCase
from unittest.mock import patch

from click.testing import CliRunner

from samcli.commands.dev.command import cli
from samcli.lib.dev import ldk


class TestDevCommand(TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_group_help_lists_the_advertised_subcommands_without_running_ldk(self):
        with patch("samcli.lib.dev.ldk.run") as run:
            result = self.runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("up", result.output)
        self.assertIn("invoke", result.output)
        run.assert_not_called()

    @patch("samcli.lib.dev.ldk.run", return_value=0)
    def test_argv_reaches_ldk_unchanged_including_function(self, run):
        result = self.runner.invoke(cli, ["up", "--function", "Orders", "--debug-port", "5678"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(run.call_args.args[:2], ("up", ["--function", "Orders", "--debug-port", "5678"]))

    @patch("samcli.lib.dev.ldk.run", return_value=4)
    def test_an_unadvertised_name_passes_through_with_its_exit_code(self, run):
        result = self.runner.invoke(cli, ["serving", "--session", "s"])
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(run.call_args.args[:2], ("serving", ["--session", "s"]))

    @patch("samcli.lib.dev.ldk.run", side_effect=ldk.SamDevError("ldk reads plugin context schema 2-2"))
    def test_a_launch_problem_is_a_usage_error(self, _run):
        result = self.runner.invoke(cli, ["up"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("schema 2-2", result.output)
