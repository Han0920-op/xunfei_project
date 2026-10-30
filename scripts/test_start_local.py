"""Launcher behavior without opening a browser or starting user processes."""
import io
import unittest
from unittest.mock import MagicMock, patch

import start_local as launcher


class LauncherTests(unittest.TestCase):
    def test_failed_start_never_opens_browser(self):
        for exit_code in [1, None]:
            process = MagicMock()
            process.poll.return_value = exit_code
            with patch.object(launcher, 'port_in_use', return_value=False), patch.object(launcher.subprocess, 'Popen', return_value=process), patch.object(launcher, 'wait_until_ready', return_value=False), patch.object(launcher.webbrowser, 'open') as browser, patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(launcher.main(), 1)
                browser.assert_not_called()
            self.assertEqual(process.terminate.called, exit_code is None)

    def test_port_collision_never_starts_or_kills_another_process(self):
        with patch.object(launcher, 'port_in_use', return_value=True), patch.object(launcher.subprocess, 'Popen') as popen, patch.object(launcher.webbrowser, 'open') as browser, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(launcher.main(), 1)
            popen.assert_not_called()
            browser.assert_not_called()

    def test_child_exit_stops_wait_without_opening(self):
        process = MagicMock()
        process.poll.return_value = 1
        with patch.object(launcher, 'ready') as ready:
            self.assertFalse(launcher.wait_until_ready(process))
            ready.assert_not_called()

    def test_ready_requires_matching_application_version_not_any_http_response(self):
        for body, expected in [(b'{"detail":"Not Found"}', False), (b'not-json', False), (b'{}', False),
                               (launcher.json.dumps({'server_version':launcher.APP_VERSION, 'stream_protocol':launcher.STREAM_PROTOCOL}).encode(), True)]:
            response = io.BytesIO(body)
            response.status = 200
            with patch.object(launcher, 'build_opener') as opener:
                opener.return_value.open.return_value = response
                self.assertEqual(launcher.ready(), expected)

    def test_success_waits_for_readiness_before_opening_and_uses_current_python(self):
        process = MagicMock()
        process.poll.return_value = 0
        process.wait.return_value = 0
        events = []
        with patch.object(launcher, 'port_in_use', return_value=False), patch.object(launcher.subprocess, 'Popen', return_value=process) as popen, patch.object(launcher, 'wait_until_ready', side_effect=lambda _: events.append('ready') or True), patch.object(launcher.webbrowser, 'open', side_effect=lambda _: events.append('browser')), patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(events, ['ready', 'browser'])
        self.assertEqual(popen.call_args.args[0][0], launcher.sys.executable)
        self.assertEqual(popen.call_args.kwargs['cwd'], launcher.BACKEND)


if __name__ == '__main__':
    unittest.main()
