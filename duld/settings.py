from abc import ABCMeta, abstractmethod
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
class TorrentData(metaclass=ABCMeta):
    """Base class for torrent client configurations"""

    type: str
    name: str | None = None


@dataclass
class TransmissionData(TorrentData):
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    download_dir: str | None = None


@dataclass
class QbittorrentData(TorrentData):
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    download_dir: str | None = None


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
    torrent_list: list[TorrentData] | None = None
    # Keep for backward compatibility
    transmission: TransmissionData | None = None
    hah_path: str | None
    dvd: DvdData | None


def load_from_path(path: str) -> Data:
    with open(path, mode="r", encoding="utf-8") as fin:
        raw_data = yaml.safe_load(fin)

        # Handle backward compatibility: convert old transmission config to torrent_list
        if "transmission" in raw_data and "torrent_list" not in raw_data:
            transmission_config = raw_data["transmission"]
            if transmission_config:
                transmission_config["type"] = "transmission"
                raw_data["torrent_list"] = [transmission_config]

        data = dacite.from_dict(Data, raw_data)
        return data
