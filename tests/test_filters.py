import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiohttp.test_utils import AioHTTPTestCase
from aiohttp.web import Application

from duld.api import FiltersHandler
from duld.filters import (
    DuplicateFilterError,
    FilterNotFoundError,
    create_filter_store,
)
from duld.keys import FILTER_STORE


class TestFilterStore(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.store = create_filter_store(f"{self._tmp.name}/duld.sqlite3")

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_initializes_database(self):
        self.assertTrue(Path(self._tmp.name, "duld.sqlite3").exists())

    def test_create_and_list_filters(self):
        first = self.store.create("abc")
        second = self.store.create("def")

        result = self.store.list()

        self.assertEqual(result, [first, second])
        self.assertEqual(first.regexp, "abc")
        self.assertEqual(second.regexp, "def")

    def test_duplicate_create_raises(self):
        self.store.create("abc")

        with self.assertRaises(DuplicateFilterError):
            self.store.create("abc")

    def test_update_filter(self):
        created = self.store.create("abc")

        updated = self.store.update(created.id, "def")

        self.assertEqual(updated.id, created.id)
        self.assertEqual(updated.regexp, "def")
        self.assertEqual(self.store.list(), [updated])

    def test_update_missing_filter_raises(self):
        with self.assertRaises(FilterNotFoundError):
            self.store.update(1, "abc")

    def test_update_duplicate_filter_raises(self):
        first = self.store.create("abc")
        self.store.create("def")

        with self.assertRaises(DuplicateFilterError):
            self.store.update(first.id, "def")

    def test_delete_filter(self):
        created = self.store.create("abc")

        self.store.delete(created.id)

        self.assertEqual(self.store.list(), [])

    def test_delete_missing_filter_raises(self):
        with self.assertRaises(FilterNotFoundError):
            self.store.delete(1)

    def test_store_path_is_used_directly(self):
        store = create_filter_store(f"{self._tmp.name}/nested/duld.sqlite3")

        store.create("abc")

        self.assertEqual(store.list()[0].regexp, "abc")
        self.assertTrue(Path(self._tmp.name, "nested", "duld.sqlite3").exists())


class TestFiltersApi(AioHTTPTestCase):
    async def asyncSetUp(self):
        self._tmp = TemporaryDirectory()
        await super().asyncSetUp()

    async def asyncTearDown(self):
        await super().asyncTearDown()
        self._tmp.cleanup()

    async def get_application(self):
        app = Application()
        store = create_filter_store(f"{self._tmp.name}/duld.sqlite3")
        app[FILTER_STORE] = store
        app.router.add_view(r"/api/v1/filters", FiltersHandler)
        app.router.add_view(r"/api/v1/filters/{filter_id:\d+}", FiltersHandler)
        return app

    async def test_get_empty_filters(self):
        response = await self.client.get("/api/v1/filters")

        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), [])

    async def test_create_filter(self):
        response = await self.client.post("/api/v1/filters", json={"regexp": "abc"})

        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"id": 1, "regexp": "abc"})

    async def test_create_empty_filter_returns_bad_request(self):
        response = await self.client.post("/api/v1/filters", json={"regexp": ""})

        self.assertEqual(response.status, 400)

    async def test_create_non_string_filter_returns_bad_request(self):
        response = await self.client.post("/api/v1/filters", json={"regexp": 123})

        self.assertEqual(response.status, 400)

    async def test_create_duplicate_filter_returns_conflict(self):
        await self.client.post("/api/v1/filters", json={"regexp": "abc"})

        response = await self.client.post("/api/v1/filters", json={"regexp": "abc"})

        self.assertEqual(response.status, 409)

    async def test_update_filter(self):
        await self.client.post("/api/v1/filters", json={"regexp": "abc"})

        response = await self.client.put("/api/v1/filters/1", json={"regexp": "def"})

        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"id": 1, "regexp": "def"})

    async def test_update_missing_filter_returns_not_found(self):
        response = await self.client.put("/api/v1/filters/1", json={"regexp": "abc"})

        self.assertEqual(response.status, 404)

    async def test_update_duplicate_filter_returns_conflict(self):
        await self.client.post("/api/v1/filters", json={"regexp": "abc"})
        await self.client.post("/api/v1/filters", json={"regexp": "def"})

        response = await self.client.put("/api/v1/filters/1", json={"regexp": "def"})

        self.assertEqual(response.status, 409)

    async def test_delete_filter(self):
        await self.client.post("/api/v1/filters", json={"regexp": "abc"})

        response = await self.client.delete("/api/v1/filters/1")

        self.assertEqual(response.status, 204)
        response = await self.client.get("/api/v1/filters")
        self.assertEqual(await response.json(), [])

    async def test_delete_missing_filter_returns_not_found(self):
        response = await self.client.delete("/api/v1/filters/1")

        self.assertEqual(response.status, 404)
