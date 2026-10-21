import os
import subprocess
from unittest import TestCase
from unittest.mock import MagicMock, patch

from samcli.lib.dev import ldk
from samcli.lib.plugins import context as pc


class TestFindLdk(TestCase):
    def test_an_explicit_path_must_exist(self):
        with patch.dict(os.environ, {ldk.LDK_PATH_ENV: "/no/such/ldk"}):
            with self.assertRaisesRegex(ldk.SamDevError, "does not exist"):
                ldk.find_ldk()

    def test_no_ldk_says_how_to_get_one(self):
        with patch.dict(os.environ, {}, clear=False), patch("samcli.lib.dev.ldk.shutil.which", return_value=None):
            os.environ.pop(ldk.LDK_PATH_ENV, None)
            with self.assertRaisesRegex(ldk.SamDevError, "no `ldk` is on PATH"):
                ldk.find_ldk()


class TestReadManifest(TestCase):
    @patch("samcli.lib.dev.ldk.subprocess.run")
    def test_the_manifest_is_read_from_ldk_itself(self, run):
        run.return_value = MagicMock(returncode=0, stdout='{"name": "ldk", "api": {"min": 1, "max": 1}}')
        self.assertEqual(ldk.read_manifest("/bin/ldk")["api"], {"min": 1, "max": 1})
        self.assertEqual(run.call_args.args[0], ["/bin/ldk", "plugin-manifest"])

    @patch("samcli.lib.dev.ldk.subprocess.run", return_value=MagicMock(returncode=2, stdout=""))
    def test_an_ldk_without_a_manifest_is_told_to_update(self, _run):
        with self.assertRaisesRegex(ldk.SamDevError, "predates sam dev"):
            ldk.read_manifest("/bin/ldk")

    @patch("samcli.lib.dev.ldk.subprocess.run", side_effect=subprocess.TimeoutExpired("ldk", 10))
    def test_a_hung_ldk_is_reported(self, _run):
        with self.assertRaisesRegex(ldk.SamDevError, "could not read"):
            ldk.read_manifest("/bin/ldk")


@patch("samcli.lib.dev.ldk.find_ldk", return_value="/bin/ldk")
class TestRun(TestCase):
    @patch("samcli.lib.plugins.launch.run", return_value=0)
    @patch("samcli.lib.plugins.context.build_context", return_value=({"schema": 1}, {"AWS_PROFILE": "p"}))
    @patch("samcli.lib.dev.ldk.read_manifest", return_value={"api": {"min": 1, "max": 1}})
    def test_every_subcommand_gets_the_context_with_its_own_args_intact(self, _manifest, build, run, _find):
        self.assertEqual(ldk.run("invoke", ["--function", "Orders", "--region", "r"], "/proj"), 0)
        self.assertEqual(build.call_args.args[0], ["dev", "invoke"])
        self.assertEqual(build.call_args.args[2].region, "r", "SAM CLI's own option is consumed")
        self.assertEqual(run.call_args.args[0], ["/bin/ldk", "invoke", "--function", "Orders"])
        self.assertEqual(run.call_args.args[3], {"schema": 1})
        self.assertEqual(run.call_args.args[4], {"AWS_PROFILE": "p"})

    @patch("samcli.lib.plugins.launch.run", return_value=0)
    @patch("samcli.lib.plugins.context.build_context")
    @patch("samcli.lib.dev.ldk.read_manifest")
    def test_help_spawns_ldk_bare(self, manifest, build, run, _find):
        ldk.run("up", ["--help"], "/proj")
        manifest.assert_not_called()
        build.assert_not_called()
        self.assertEqual(run.call_args.args[0], ["/bin/ldk", "up", "--help"])
        self.assertIsNone(run.call_args.args[3])

    @patch("samcli.lib.plugins.launch.run")
    @patch("samcli.lib.dev.ldk.read_manifest", return_value={"api": {"min": 2, "max": 2}})
    def test_an_api_mismatch_stops_before_anything_runs(self, _manifest, run, _find):
        with self.assertRaisesRegex(ldk.SamDevError, "Update SAM CLI"):
            ldk.run("up", [], "/proj")
        run.assert_not_called()

    @patch("samcli.lib.dev.ldk.read_manifest", return_value={"api": {"min": 1, "max": 1}})
    @patch("samcli.lib.plugins.context.build_context", side_effect=pc.PluginContextError("no template at /x"))
    def test_a_context_problem_is_a_sam_dev_error(self, _build, _manifest, _find):
        with self.assertRaisesRegex(ldk.SamDevError, "no template at /x"):
            ldk.run("up", ["-t", "/x"], "/proj")
