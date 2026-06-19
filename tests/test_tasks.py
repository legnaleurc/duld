import unittest

from duld.tasks import UploadTaskManager


class _FakeGroup:
    def __init__(self):
        self.coroutines = []

    def create_task(self, coro):
        self.coroutines.append(coro)


class TestUploadTaskManager(unittest.IsolatedAsyncioTestCase):
    async def test_create_once_skips_duplicate_before_task_finishes(self):
        group = _FakeGroup()
        manager = UploadTaskManager(group)
        calls = 0

        async def run():
            nonlocal calls
            calls += 1

        self.assertTrue(manager.create_once(("torrent", 1), run))
        self.assertFalse(manager.create_once(("torrent", 1), run))
        self.assertEqual(calls, 0)
        self.assertEqual(len(group.coroutines), 1)

        await group.coroutines[0]
        self.assertEqual(calls, 1)

    async def test_create_once_releases_key_after_task_finishes(self):
        group = _FakeGroup()
        manager = UploadTaskManager(group)

        async def run():
            pass

        self.assertTrue(manager.create_once(("torrent", 1), run))
        await group.coroutines.pop()

        self.assertTrue(manager.create_once(("torrent", 1), run))
        await group.coroutines.pop()

    async def test_create_once_releases_key_after_task_fails(self):
        group = _FakeGroup()
        manager = UploadTaskManager(group)

        async def fail():
            raise RuntimeError("boom")

        self.assertTrue(manager.create_once(("torrent", 1), fail))
        with self.assertRaises(RuntimeError):
            await group.coroutines.pop()

        async def run():
            pass

        self.assertTrue(manager.create_once(("torrent", 1), run))
        await group.coroutines.pop()
