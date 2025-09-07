"""
Torrent client package for supporting multiple torrent clients.

This package provides:
- Abstract torrent client interface
- Transmission client implementation
- Client registry for managing multiple clients
- Common torrent operations
"""

from .client import TorrentClient, TorrentFile, TorrentInfo, TorrentSession
from .ops import (
    add_urls,
    get_completed,
    upload_by_id,
    watch_disk_space,
)
from .qbittorrent import QbittorrentClient
from .registry import (
    TorrentClientRegistry,
    create_torrent_client,
    create_torrent_registry,
)
from .transmission import TransmissionClient


__all__ = [
    # Core interfaces and models
    "TorrentClient",
    "TorrentFile",
    "TorrentInfo",
    "TorrentSession",
    # Client implementations
    "TransmissionClient",
    "QbittorrentClient",
    # Registry and factory functions
    "TorrentClientRegistry",
    "create_torrent_client",
    "create_torrent_registry",
    # Operations
    "add_urls",
    "get_completed",
    "upload_by_id",
    "watch_disk_space",
]
