import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from duld.hah import (
    _get_gid_from_name,
    _get_names_for_upload,
    _is_src_too_long,
    _read_title_from_meta,
    _shorten_remote_name,
)


class TestIsSrcTooLong(unittest.TestCase):
    def test_numeric_only_is_too_long(self):
        self.assertTrue(_is_src_too_long("1234567"))

    def test_alphabetic_is_not_too_long(self):
        self.assertFalse(_is_src_too_long("SomeTitle"))

    def test_mixed_alphanumeric_is_not_too_long(self):
        self.assertFalse(_is_src_too_long("Title123"))

    def test_title_with_brackets_is_not_too_long(self):
        self.assertFalse(_is_src_too_long("Some Title [12345]"))

    def test_empty_string_is_not_too_long(self):
        self.assertFalse(_is_src_too_long(""))


class TestGetGidFromName(unittest.TestCase):
    def test_extracts_numeric_gid(self):
        self.assertEqual(_get_gid_from_name("Some Title [12345]"), "12345")

    def test_extracts_gid_at_end(self):
        self.assertEqual(_get_gid_from_name("A B C [999]"), "999")

    def test_raises_when_no_brackets(self):
        with self.assertRaises(ValueError):
            _get_gid_from_name("No brackets here")

    def test_raises_when_brackets_not_at_end(self):
        with self.assertRaises(ValueError):
            _get_gid_from_name("[12345] Title at front")

    def test_raises_when_bracket_content_is_not_numeric(self):
        with self.assertRaises(ValueError):
            _get_gid_from_name("Title [abc]")


class TestReadTitleFromMeta(unittest.TestCase):
    def test_reads_title_line(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "galleryinfo.txt").write_text(
                "Title: My Gallery\nOther: value\n", encoding="utf-8"
            )
            self.assertEqual(_read_title_from_meta(path), "My Gallery")

    def test_title_with_colon_in_value(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "galleryinfo.txt").write_text("Title: Foo: Bar\n", encoding="utf-8")
            self.assertEqual(_read_title_from_meta(path), "Foo: Bar")

    def test_title_is_stripped(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "galleryinfo.txt").write_text(
                "Title:  Padded Title  \n", encoding="utf-8"
            )
            self.assertEqual(_read_title_from_meta(path), "Padded Title")

    def test_raises_when_no_title(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "galleryinfo.txt").write_text("Other: value\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                _read_title_from_meta(path)


class TestShortenRemoteName(unittest.TestCase):
    def _make_gallery(self, parent: Path, name: str, title: str) -> Path:
        gallery = parent / name
        gallery.mkdir()
        (gallery / "galleryinfo.txt").write_text(f"Title: {title}\n", encoding="utf-8")
        return gallery

    def test_short_enough_returns_title_gid_format(self):
        with TemporaryDirectory() as tmp:
            gallery = self._make_gallery(Path(tmp), "Short Title [999]", "Short Title")
            result = _shorten_remote_name(gallery, "Short Title [999].7z")
            self.assertEqual(result, "Short Title [999].7z")

    def test_result_fits_within_255_bytes(self):
        with TemporaryDirectory() as tmp:
            long_title = "A" * 300
            gallery = self._make_gallery(Path(tmp), "Some Name [12345]", long_title)
            result = _shorten_remote_name(gallery, f"{long_title} [12345].7z")
            self.assertLessEqual(len(result.encode("utf-8")), 255)

    def test_shortened_result_contains_gid(self):
        with TemporaryDirectory() as tmp:
            long_title = "B" * 300
            gallery = self._make_gallery(Path(tmp), "Long Name [99999]", long_title)
            result = _shorten_remote_name(gallery, f"{long_title} [99999].7z")
            self.assertIn("[99999]", result)

    def test_unicode_title_truncated_correctly(self):
        with TemporaryDirectory() as tmp:
            # Each CJK char is 3 bytes; 80 chars = 240 bytes, plus gid_part pushes over 255
            cjk_title = "あ" * 80
            gallery = self._make_gallery(Path(tmp), "日本語 [77777]", cjk_title)
            result = _shorten_remote_name(gallery, f"{cjk_title} [77777].7z")
            self.assertLessEqual(len(result.encode("utf-8")), 255)


class TestGetNamesForUpload(unittest.TestCase):
    def _make_gallery(self, parent: Path, name: str, title: str) -> Path:
        gallery = parent / name
        gallery.mkdir()
        (gallery / "galleryinfo.txt").write_text(f"Title: {title}\n", encoding="utf-8")
        return gallery

    def test_normal_name_returns_name_and_7z(self):
        with TemporaryDirectory() as tmp:
            src = self._make_gallery(Path(tmp), "Normal Title [12345]", "Normal Title")
            dst = Path(tmp) / "dst"
            dst.mkdir()
            base, remote = _get_names_for_upload(src, dst)
            self.assertEqual(base, "Normal Title [12345]")
            self.assertEqual(remote, "Normal Title [12345].7z")

    def test_numeric_name_uses_title_gid_as_remote(self):
        with TemporaryDirectory() as tmp:
            src = self._make_gallery(Path(tmp), "1234567", "My Gallery")
            dst = Path(tmp) / "dst"
            dst.mkdir()
            base, remote = _get_names_for_upload(src, dst)
            self.assertEqual(base, "1234567")
            self.assertEqual(remote, "My Gallery [1234567].7z")

    def test_compress_name_too_long_uses_gid_as_base(self):
        with TemporaryDirectory() as tmp:
            name = "A" * 200 + " [99999]"
            src = Path(tmp) / name
            src.mkdir()
            dst = Path(tmp) / "dst"
            dst.mkdir()
            with patch("duld.hah.is_too_long_to_compress", return_value=True):
                base, remote = _get_names_for_upload(src, dst)
            self.assertEqual(base, "99999")
            self.assertEqual(remote, f"{name}.7z")
