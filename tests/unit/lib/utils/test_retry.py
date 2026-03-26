from unittest import TestCase
from unittest.mock import patch

from samcli.lib.utils.retry import retry


class TestRetryExceptionChaining(TestCase):
    @patch("samcli.lib.utils.retry.time.sleep")
    def test_exception_chaining_preserves_original_cause(self, mock_sleep):
        @retry(exc=ValueError, attempts=2, delay=0, exc_raise=RuntimeError, exc_raise_msg="failed")
        def failing():
            raise ValueError("original error")

        with self.assertRaises(RuntimeError) as ctx:
            failing()

        self.assertIsNotNone(ctx.exception.__cause__)
        self.assertIsInstance(ctx.exception.__cause__, ValueError)
        self.assertEqual(str(ctx.exception.__cause__), "original error")
