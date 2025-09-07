import logging
from typing import override

from transmission_rpc import Client, Torrent, TransmissionError

from ..settings import TransmissionData
from .client import TorrentClient, TorrentFile, TorrentInfo, TorrentSession


_L = logging.getLogger(__name__)


class TransmissionClient(TorrentClient):
    """Transmission torrent client implementation"""

    def __init__(self, config: TransmissionData) -> None:
        super().__init__(config)
        self._client: Client | None = None

    def _get_client(self) -> Client:
        """Get or create Transmission client connection"""
        if self._client is None:
            self._client = Client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            )
        return self._client

    @override
    def get_torrent(self, torrent_id: str) -> TorrentInfo | None:
        try:
            client = self._get_client()
            torrent = client.get_torrent(int(torrent_id))
            if not torrent:
                return None
            return self._convert_torrent(torrent)
        except (ValueError, TransmissionError) as e:
            _L.error(f"Failed to get torrent {torrent_id}: {e}")
            return None

    @override
    def get_torrents(self) -> list[TorrentInfo]:
        try:
            client = self._get_client()
            torrents = client.get_torrents()
            return [self._convert_torrent(t) for t in torrents]
        except TransmissionError as e:
            _L.error(f"Failed to get torrents: {e}")
            return []

    @override
    def add_torrent(self, url: str, paused: bool = True) -> TorrentInfo | None:
        try:
            client = self._get_client()
            torrent = client.add_torrent(url, paused=paused)
            if not torrent:
                return None
            return self._convert_torrent(torrent)
        except TransmissionError as e:
            _L.error(f"Failed to add torrent {url}: {e}")
            return None

    @override
    def remove_torrent(self, torrent_id: str, delete_data: bool = True) -> None:
        try:
            client = self._get_client()
            client.remove_torrent(int(torrent_id), delete_data=delete_data)
            _L.info(f"Removed torrent {torrent_id}")
        except (ValueError, TransmissionError) as e:
            _L.error(f"Failed to remove torrent {torrent_id}: {e}")

    @override
    def get_session(self) -> TorrentSession:
        try:
            client = self._get_client()
            session = client.get_session()
            return TorrentSession(download_dir=session.download_dir)
        except TransmissionError as e:
            _L.error(f"Failed to get session: {e}")
            raise

    @override
    def free_space(self, path: str) -> int | None:
        try:
            client = self._get_client()
            return client.free_space(path)
        except TransmissionError as e:
            _L.error(f"Failed to get free space for {path}: {e}")
            return None

    @override
    def start_torrent(self, torrent_ids: list[str]) -> None:
        try:
            client = self._get_client()
            int_ids = [int(tid) for tid in torrent_ids]
            client.start_torrent(int_ids)
        except (ValueError, TransmissionError) as e:
            _L.error(f"Failed to start torrents {torrent_ids}: {e}")

    @override
    def stop_torrent(self, torrent_ids: list[str]) -> None:
        try:
            client = self._get_client()
            int_ids = [int(tid) for tid in torrent_ids]
            client.stop_torrent(int_ids)
        except (ValueError, TransmissionError) as e:
            _L.error(f"Failed to stop torrents {torrent_ids}: {e}")

    def _convert_torrent(self, torrent: Torrent) -> TorrentInfo:
        """Convert Transmission Torrent to common TorrentInfo"""
        files = torrent.get_files()
        torrent_files = [
            TorrentFile(name=file.name, size=file.size, selected=file.selected)
            for file in files
        ]

        return TorrentInfo(
            id=str(torrent.id),
            name=torrent.name,
            status=torrent.status,
            download_dir=torrent.download_dir,
            downloaded_ever=torrent.downloaded_ever,
            left_until_done=torrent.left_until_done,
            files=torrent_files,
        )
