import unittest
from unittest.mock import MagicMock

from duld.torrent import _get_root_dir, _get_root_items, _split_all


class TestSplitAll(unittest.TestCase):
    def test_single_component(self):
        self.assertEqual(_split_all("a"), ["a"])

    def test_relative_nested(self):
        self.assertEqual(_split_all("a/b/c"), ["a", "b", "c"])

    def test_relative_two_parts(self):
        self.assertEqual(_split_all("a/b"), ["a", "b"])

    def test_absolute_path(self):
        self.assertEqual(_split_all("/a/b"), ["/", "a", "b"])

    def test_absolute_single(self):
        self.assertEqual(_split_all("/a"), ["/", "a"])


class TestGetRootItems(unittest.TestCase):
    def _make_file(self, name: str, selected: bool):
        f = MagicMock()
        f.name = name
        f.selected = selected
        return f

    def test_returns_top_level_dir(self):
        torrent = MagicMock()
        torrent.get_files.return_value = [
            self._make_file("folder/a.txt", True),
            self._make_file("folder/b.txt", True),
        ]
        self.assertEqual(_get_root_items(torrent), ["folder"])

    def test_excludes_unselected_files(self):
        torrent = MagicMock()
        torrent.get_files.return_value = [
            self._make_file("a/x.txt", True),
            self._make_file("b/y.txt", False),
        ]
        self.assertEqual(_get_root_items(torrent), ["a"])

    def test_multiple_root_dirs(self):
        torrent = MagicMock()
        torrent.get_files.return_value = [
            self._make_file("a/x.txt", True),
            self._make_file("b/y.txt", True),
        ]
        self.assertEqual(sorted(_get_root_items(torrent)), ["a", "b"])

    def test_deduplicates_same_root(self):
        torrent = MagicMock()
        torrent.get_files.return_value = [
            self._make_file("folder/a.txt", True),
            self._make_file("folder/b.txt", True),
            self._make_file("folder/sub/c.txt", True),
        ]
        self.assertEqual(_get_root_items(torrent), ["folder"])

    def test_no_selected_files(self):
        torrent = MagicMock()
        torrent.get_files.return_value = [
            self._make_file("a/x.txt", False),
        ]
        self.assertEqual(_get_root_items(torrent), [])

    def test_empty_file_list(self):
        torrent = MagicMock()
        torrent.get_files.return_value = []
        self.assertEqual(_get_root_items(torrent), [])


class TestGetRootDir(unittest.TestCase):
    def test_explicit_download_dir_takes_precedence(self):
        torrent = MagicMock()
        torrent.download_dir = "/torrent/dir"
        self.assertEqual(_get_root_dir(torrent, "/explicit/dir"), "/explicit/dir")

    def test_falls_back_to_torrent_download_dir(self):
        torrent = MagicMock()
        torrent.download_dir = "/torrent/dir"
        self.assertEqual(_get_root_dir(torrent, None), "/torrent/dir")

    def test_empty_string_download_dir_falls_back(self):
        torrent = MagicMock()
        torrent.download_dir = "/downloads"
        self.assertEqual(_get_root_dir(torrent, ""), "/downloads")
