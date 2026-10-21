import json
import os
import signal
from unittest import TestCase
from unittest.mock import MagicMock, patch

from samcli.lib.plugins import launch


class TestCheckApi(TestCase):
    def test_a_range_holding_this_schema_is_accepted(self):
        launch.check_api({"api": {"min": 1, "max": 3}}, "ldk")

    def test_an_older_plugin_is_told_to_update(self):
        with patch.object(launch, "CONTEXT_SCHEMA", 2):
            with self.assertRaisesRegex(launch.PluginLaunchError, "reads plugin context schema 1-1.*writes schema 2.*Update ldk"):
                launch.check_api({"api": {"min": 1, "max": 1}}, "ldk")

    def test_a_newer_plugin_asks_for_a_newer_sam_cli(self):
        with self.assertRaisesRegex(launch.PluginLaunchError, "Update SAM CLI"):
            launch.check_api({"api": {"min": 2, "max": 2}}, "ldk")

    def test_no_range_is_refused(self):
        with self.assertRaisesRegex(launch.PluginLaunchError, "declares no api range"):
            launch.check_api({}, "ldk")


class TestRun(TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(launch.DEPTH_ENV, None)

    @patch("samcli.lib.plugins.launch.subprocess.Popen")
    def test_the_plugin_gets_the_context_and_its_exit_code_is_returned(self, popen):
        seen = {}

        def start(argv, env):
            seen["argv"], seen["env"] = argv, env
            with open(env["SAM_CONTEXT_FILE"]) as f:
                seen["context"] = json.load(f)
            proc = MagicMock()
            proc.wait.return_value = 3
            proc.poll.return_value = 3
            return proc

        popen.side_effect = start
        code = launch.run(["/bin/ldk", "up", "--x"], ["dev", "up"], "/proj", {"schema": 1}, {"AWS_PROFILE": "p"})

        self.assertEqual(code, 3)
        self.assertEqual(seen["argv"], ["/bin/ldk", "up", "--x"])
        env = seen["env"]
        self.assertEqual(
            (env["SAM_PLUGIN_API"], env["SAM_COMMAND_PATH"], env["SAM_PROJECT_ROOT"], env["AWS_PROFILE"]),
            ("1", "dev.up", "/proj", "p"),
        )
        self.assertEqual(seen["context"], {"schema": 1})
        self.assertFalse(os.path.exists(env["SAM_CONTEXT_FILE"]), "the context file is deleted after the plugin exits")

    @patch("samcli.lib.plugins.launch.subprocess.Popen")
    def test_no_context_means_no_context_file(self, popen):
        popen.return_value.wait.return_value = 0
        launch.run(["/bin/ldk", "up", "--help"], ["dev", "up"], "/proj", None, {})
        self.assertNotIn("SAM_CONTEXT_FILE", popen.call_args.kwargs["env"])

    @patch("samcli.lib.plugins.launch.subprocess.Popen")
    def test_ctrl_c_waits_for_the_plugin_instead_of_killing_it(self, popen):
        proc = MagicMock()
        proc.wait.side_effect = [KeyboardInterrupt, KeyboardInterrupt, 0]
        popen.return_value = proc
        self.assertEqual(launch.run(["/bin/ldk", "up"], ["dev", "up"], "/proj", None, {}), 0)
        self.assertEqual(proc.wait.call_count, 3)
        proc.kill.assert_not_called()
        proc.terminate.assert_not_called()

    def test_a_callback_cannot_start_a_second_plugin(self):
        os.environ[launch.DEPTH_ENV] = "1"
        with self.assertRaisesRegex(launch.PluginLaunchError, "already running"):
            launch.run(["/bin/ldk", "up"], ["dev", "up"], "/proj", None, {})

    @patch("samcli.lib.plugins.launch.subprocess.Popen")
    def test_sigterm_is_forwarded_and_the_handler_restored(self, popen):
        proc = MagicMock()
        proc.poll.return_value = None

        def wait():
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            return 0

        proc.wait.side_effect = wait
        popen.return_value = proc
        before = signal.getsignal(signal.SIGTERM)
        launch.run(["/bin/ldk", "up"], ["dev", "up"], "/proj", None, {})
        proc.send_signal.assert_called_once_with(signal.SIGTERM)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)
