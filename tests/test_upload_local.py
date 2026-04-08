import unittest
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory

from duld.upload._core import UploadError
from duld.upload._local import LocalBackend


class TestLocalBackend(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.backend = LocalBackend(upload_to=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_get_root_folder(self):
        result = await self.backend.get_root_folder()
        self.assertEqual(result, self.root)

    async def test_get_child_returns_path_when_exists(self):
        child = self.root / "folder"
        child.mkdir()
        result = await self.backend.get_child("folder", self.root)
        self.assertEqual(result, child)

    async def test_get_child_returns_none_when_missing(self):
        result = await self.backend.get_child("missing", self.root)
        self.assertIsNone(result)

    async def test_create_folder_creates_directory(self):
        result = await self.backend.create_folder("new_dir", self.root)
        self.assertTrue(result.is_dir())
        self.assertEqual(result.name, "new_dir")

    async def test_create_folder_is_idempotent(self):
        await self.backend.create_folder("new_dir", self.root)
        result = await self.backend.create_folder("new_dir", self.root)
        self.assertTrue(result.is_dir())

    async def test_upload_file_copies_content(self):
        src = self.root / "source.txt"
        src.write_bytes(b"hello")
        dest_dir = self.root / "dest"
        dest_dir.mkdir()
        result = await self.backend.upload_file(src, dest_dir, name="source.txt")
        self.assertTrue(result.is_file())
        self.assertEqual(result.read_bytes(), b"hello")

    async def test_upload_file_uses_given_name(self):
        src = self.root / "source.txt"
        src.write_bytes(b"data")
        dest_dir = self.root / "dest"
        dest_dir.mkdir()
        result = await self.backend.upload_file(src, dest_dir, name="renamed.txt")
        self.assertEqual(result.name, "renamed.txt")

    async def test_verify_file_same_size_does_not_raise(self):
        f = self.root / "file.txt"
        f.write_bytes(b"hello")
        await self.backend.verify_file(f, f, PurePath("/remote/file.txt"))

    async def test_verify_file_size_mismatch_raises(self):
        local = self.root / "local.txt"
        local.write_bytes(b"hello")
        remote = self.root / "remote.txt"
        remote.write_bytes(b"world!")
        with self.assertRaises(UploadError):
            await self.backend.verify_file(
                local, remote, PurePath("/remote/remote.txt")
            )

    async def test_resolve_path_returns_pure_path(self):
        result = await self.backend.resolve_path(self.root)
        self.assertEqual(result, PurePath(self.root))

    async def test_sync_does_nothing(self):
        await self.backend.sync()

    async def test_ensure_entry_exists_ok_for_existing_path(self):
        await self.backend.ensure_entry_exists(self.root)

    async def test_ensure_entry_exists_raises_for_missing_path(self):
        missing = self.root / "nope"
        with self.assertRaises(UploadError):
            await self.backend.ensure_entry_exists(missing)

    async def test_is_trashed_always_false(self):
        self.assertFalse(await self.backend.is_trashed(self.root))

    async def test_is_directory_true_for_dir(self):
        self.assertTrue(await self.backend.is_directory(self.root))

    async def test_is_directory_false_for_file(self):
        f = self.root / "file.txt"
        f.write_text("x", encoding="utf-8")
        self.assertFalse(await self.backend.is_directory(f))
