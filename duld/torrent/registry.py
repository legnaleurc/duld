import logging
from typing import Any

from ..settings import QbittorrentData, TorrentData, TransmissionData
from .client import TorrentClient
from .qbittorrent import QbittorrentClient
from .transmission import TransmissionClient


_L = logging.getLogger(__name__)


class TorrentClientRegistry:
    """Registry for managing multiple torrent clients"""

    def __init__(self) -> None:
        self._clients: dict[str, TorrentClient] = {}

    def register_client(self, client: TorrentClient) -> None:
        """Register a torrent client"""
        self._clients[client.name] = client
        _L.info(f"Registered torrent client: {client.name}")

    def get_client(self, name: str) -> TorrentClient | None:
        """Get a torrent client by name"""
        return self._clients.get(name)

    def get_all_clients(self) -> dict[str, TorrentClient]:
        """Get all registered clients"""
        return self._clients.copy()

    def get_default_client(self) -> TorrentClient | None:
        """Get the first available client as default"""
        if not self._clients:
            return None
        return next(iter(self._clients.values()))


def create_torrent_client(config: TorrentData) -> TorrentClient | None:
    """Factory function to create torrent clients based on configuration"""
    if config.type == "transmission":
        if not isinstance(config, TransmissionData):
            _L.error(f"Invalid transmission config: {config}")
            return None
        return TransmissionClient(config)
    elif config.type == "qbittorrent":
        if not isinstance(config, QbittorrentData):
            _L.error(f"Invalid qbittorrent config: {config}")
            return None
        return QbittorrentClient(config)
    else:
        _L.error(f"Unsupported torrent client type: {config.type}")
        return None


def create_torrent_registry(configs: list[TorrentData] | None) -> TorrentClientRegistry:
    """Create and populate a torrent client registry from configurations"""
    registry = TorrentClientRegistry()

    if not configs:
        return registry

    for config in configs:
        client = create_torrent_client(config)
        if client:
            registry.register_client(client)

    return registry
