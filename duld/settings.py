from dataclasses import dataclass

import dacite
import yaml


@dataclass
class ExcludeData:
    static: list[str] | None
    dynamic: str | None


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
    download_dir: str | None


@dataclass
class DvdData:
    caches_searches_url: str
    token: str | None


@dataclass
class Data:
    host: str
    port: int
    drive_config_path: str
    upload_to: str
    log_path: str | None
    exclude: ExcludeData | None
    reserved_space_in_gb: DiskSpaceData | None
    transmission: TransmissionData | None
    hah_path: str | None
    dvd: DvdData | None


def load_from_path(path: str) -> Data:
    with open(path, mode="r", encoding="utf-8") as fin:
        raw_data = yaml.safe_load(fin)
        data = dacite.from_dict(Data, raw_data)
        return data
