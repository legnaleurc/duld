import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from duld.settings import load_from_path


_MINIMAL_CONFIG = """\
host: "0.0.0.0"
port: 8080
upload:
  type: local
  kwargs:
    upload_to: /tmp/upload
log_path: null
exclude: null
reserved_space_in_gb: null
transmission: null
hah_path: null
max_jobs: null
"""


class TestLoadFromPath(unittest.TestCase):
    def _write_config(self, tmp: str, content: str) -> str:
        path = str(Path(tmp) / "config.yaml")
        Path(path).write_text(content, encoding="utf-8")
        return path

    def test_minimal_config_loads(self):
        with TemporaryDirectory() as tmp:
            path = self._write_config(tmp, _MINIMAL_CONFIG)
            data = load_from_path(path)
            self.assertEqual(data.host, "0.0.0.0")
            self.assertEqual(data.port, 8080)
            self.assertEqual(data.upload.type, "local")
            self.assertIsNone(data.max_jobs)

    def test_max_jobs_zero_is_valid(self):
        with TemporaryDirectory() as tmp:
            config = _MINIMAL_CONFIG.replace("max_jobs: null", "max_jobs: 0")
            path = self._write_config(tmp, config)
            data = load_from_path(path)
            self.assertEqual(data.max_jobs, 0)

    def test_max_jobs_positive_is_valid(self):
        with TemporaryDirectory() as tmp:
            config = _MINIMAL_CONFIG.replace("max_jobs: null", "max_jobs: 4")
            path = self._write_config(tmp, config)
            data = load_from_path(path)
            self.assertEqual(data.max_jobs, 4)

    def test_max_jobs_negative_raises(self):
        with TemporaryDirectory() as tmp:
            config = _MINIMAL_CONFIG.replace("max_jobs: null", "max_jobs: -1")
            path = self._write_config(tmp, config)
            with self.assertRaises(ValueError):
                load_from_path(path)

    def test_exclude_static_list_is_loaded(self):
        with TemporaryDirectory() as tmp:
            config = _MINIMAL_CONFIG.replace(
                "exclude: null",
                "exclude:\n  static:\n    - pattern1\n    - pattern2\n  dynamic: null",
            )
            path = self._write_config(tmp, config)
            data = load_from_path(path)
            self.assertIsNotNone(data.exclude)
            self.assertEqual(data.exclude.static, ["pattern1", "pattern2"])
