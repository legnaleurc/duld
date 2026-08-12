import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from duld.upload._core import _DefaultUploader


class _PermanentError(Exception):
    retryable = False


class _NameTooLongError(_PermanentError):
    reason = "name_too_long"


class TestUploadRetry(unittest.IsolatedAsyncioTestCase):
    async def test_permanent_error_is_not_retried(self):
        backend = MagicMock()
        backend.sync = AsyncMock()
        uploader = _DefaultUploader(backend=backend, dfd_client=MagicMock())
        uploader._upload_file = AsyncMock(side_effect=_PermanentError("stop"))

        with self.assertRaises(_PermanentError):
            await uploader._upload_file_retry(
                MagicMock(), Path("file.bin"), remote_name="file.bin"
            )

        uploader._upload_file.assert_awaited_once()
        backend.sync.assert_not_awaited()

    async def test_name_too_long_retries_once_with_shortened_remote_name(self):
        backend = MagicMock()
        backend.sync = AsyncMock()
        uploader = _DefaultUploader(backend=backend, dfd_client=MagicMock())
        uploader._upload_file = AsyncMock(
            side_effect=[_NameTooLongError("too long"), None]
        )
        original = f"{'あ' * 100} [7777777].7z"

        await uploader._upload_file_retry(
            MagicMock(), Path("file.7z"), remote_name=original
        )

        calls = uploader._upload_file.await_args_list
        self.assertEqual(calls[0].kwargs["remote_name"], original)
        shortened = calls[1].kwargs["remote_name"]
        self.assertLessEqual(len(shortened.encode("utf-8")), 255)
        self.assertTrue(shortened.endswith(".7z"))
        backend.sync.assert_not_awaited()
