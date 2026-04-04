from dataclasses import dataclass
from typing import Any

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
class UploadData:
    type: str
    kwargs: dict[str, Any] | None


@dataclass
class Data:
    host: str
    port: int
    upload: UploadData
    log_path: str | None
    exclude: ExcludeData | None
    reserved_space_in_gb: DiskSpaceData | None
    transmission: TransmissionData | None
    hah_path: str | None
    max_jobs: int | None


def load_from_path(path: str) -> Data:
    with open(path, mode="r", encoding="utf-8") as fin:
        raw_data = yaml.safe_load(fin)
        data = dacite.from_dict(Data, raw_data)
        if data.max_jobs is not None and data.max_jobs < 0:
            raise ValueError(f"max_jobs must be >= 0, got {data.max_jobs}")
        return data
