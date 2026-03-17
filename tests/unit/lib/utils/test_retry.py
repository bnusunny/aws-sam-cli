import pytest
from samcli.lib.utils.retry import retry


def test_retry_preserves_exception_chain():
    @retry(exc=ValueError, attempts=2, delay=0, exc_raise=RuntimeError, exc_raise_msg="failed")
    def failing():
        raise ValueError("original")

    with pytest.raises(RuntimeError) as exc_info:
        failing()

    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert str(exc_info.value.__cause__) == "original"
