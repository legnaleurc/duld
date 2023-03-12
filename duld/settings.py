from dataclasses import dataclass
import sys
import dacite

import yaml


@dataclass
class DiskSpaceData:
    safe: int
    danger: int


@dataclass
class TransmissionData:
    host: str
    port: int
    username: str | None
    password: str | None


@dataclass
class Data:
    port: int
    upload_to: str
    log_path: str | None
    exclude_pattern: list[str] | None
    exclude_url: str | None
    reserved_space_in_gb: DiskSpaceData | None
    transmission: TransmissionData | None
    hah_path: str | None


def load_from_path(path: str) -> Data:
    with open(path, mode="r", encoding="utf-8") as fin:
        raw_data = yaml.safe_load(fin)
        data = dacite.from_dict(Data, raw_data)
        return data


class Settings(object):
    def __init__(self):
        self._data = None

    def __getitem__(self, key):
        return self._data[key]

    def reload(self, path):
        with open(path, mode="r", encoding="utf-8") as fin:
            self._data = yaml.safe_load(fin)


sys.modules[__name__] = Settings()
