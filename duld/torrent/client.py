from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class TorrentFile:
    """Represents a file within a torrent"""

    name: str
    size: int
    selected: bool


@dataclass
class TorrentInfo:
    """Common torrent information across different clients"""

    id: str  # Generic string ID to support different client ID types
    name: str
    status: str
    download_dir: str
    downloaded_ever: int
    left_until_done: int
    files: list[TorrentFile]


@dataclass
class TorrentSession:
    """Session information for disk space monitoring"""

    download_dir: str


class TorrentClient(metaclass=ABCMeta):
    """Abstract base class for torrent client implementations"""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.name = getattr(config, "name", None) or f"{config.type}_client"

    @abstractmethod
    def get_torrent(self, torrent_id: str) -> TorrentInfo | None:
        """Get a specific torrent by ID"""
        pass

    @abstractmethod
    def get_torrents(self) -> list[TorrentInfo]:
        """Get all torrents"""
        pass

    @abstractmethod
    def add_torrent(self, url: str, paused: bool = True) -> TorrentInfo | None:
        """Add a new torrent from URL"""
        pass

    @abstractmethod
    def remove_torrent(self, torrent_id: str, delete_data: bool = True) -> None:
        """Remove a torrent"""
        pass

    @abstractmethod
    def get_session(self) -> TorrentSession:
        """Get session information"""
        pass

    @abstractmethod
    def free_space(self, path: str) -> int | None:
        """Get free space in bytes for the given path"""
        pass

    @abstractmethod
    def start_torrent(self, torrent_ids: list[str]) -> None:
        """Start torrents"""
        pass

    @abstractmethod
    def stop_torrent(self, torrent_ids: list[str]) -> None:
        """Stop torrents"""
        pass
