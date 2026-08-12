import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from duld.upload._core import _DefaultUploader


class _PermanentError(Exception):
    retryable = False


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
