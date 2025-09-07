import logging
from typing import override

from qbittorrentapi import Client, TorrentDictionary, TorrentsAPIMixIn
from qbittorrentapi.exceptions import APIConnectionError, LoginFailed

from ..settings import QbittorrentData
from .client import TorrentClient, TorrentFile, TorrentInfo, TorrentSession


_L = logging.getLogger(__name__)


class QbittorrentClient(TorrentClient):
    """qBittorrent torrent client implementation"""

    def __init__(self, config: QbittorrentData) -> None:
        super().__init__(config)
        self._client: Client | None = None

    def _get_client(self) -> Client:
        """Get or create qBittorrent client connection"""
        if self._client is None:
            self._client = Client(
                host=f"http://{self.config.host}:{self.config.port}",
                username=self.config.username,
                password=self.config.password,
            )
            try:
                self._client.auth_log_in()
            except LoginFailed as e:
                _L.error(f"Failed to login to qBittorrent: {e}")
                raise
            except APIConnectionError as e:
                _L.error(f"Failed to connect to qBittorrent: {e}")
                raise
        return self._client

    @override
    def get_torrent(self, torrent_id: str) -> TorrentInfo | None:
        try:
            client = self._get_client()
            torrents = client.torrents_info(torrent_hashes=torrent_id)
            if not torrents:
                return None
            torrent = torrents[0]
            return self._convert_torrent(torrent)
        except Exception as e:
            _L.error(f"Failed to get torrent {torrent_id}: {e}")
            return None

    @override
    def get_torrents(self) -> list[TorrentInfo]:
        try:
            client = self._get_client()
            torrents = client.torrents_info()
            return [self._convert_torrent(t) for t in torrents]
        except Exception as e:
            _L.error(f"Failed to get torrents: {e}")
            return []

    @override
    def add_torrent(self, url: str, paused: bool = True) -> TorrentInfo | None:
        try:
            client = self._get_client()
            # Add torrent with paused state
            client.torrents_add(
                urls=url,
                is_paused=paused,
                savepath=self.config.download_dir,
            )
            # Get the added torrent (qBittorrent doesn't return the torrent object directly)
            # We'll need to find it by matching the URL or name
            torrents = client.torrents_info()
            # This is a simplified approach - in practice, you might need more sophisticated matching
            for torrent in torrents:
                if torrent.state_enum.is_paused == paused:
                    return self._convert_torrent(torrent)
            return None
        except Exception as e:
            _L.error(f"Failed to add torrent {url}: {e}")
            return None

    @override
    def remove_torrent(self, torrent_id: str, delete_data: bool = True) -> None:
        try:
            client = self._get_client()
            client.torrents_delete(torrent_hashes=torrent_id, delete_files=delete_data)
            _L.info(f"Removed torrent {torrent_id}")
        except Exception as e:
            _L.error(f"Failed to remove torrent {torrent_id}: {e}")

    @override
    def get_session(self) -> TorrentSession:
        try:
            client = self._get_client()
            preferences = client.app_preferences()
            download_dir = preferences.get("save_path", "/downloads")
            return TorrentSession(download_dir=download_dir)
        except Exception as e:
            _L.error(f"Failed to get session: {e}")
            raise

    @override
    def free_space(self, path: str) -> int | None:
        try:
            client = self._get_client()
            # qBittorrent doesn't have a direct free space API
            # We'll use the default download directory from preferences
            preferences = client.app_preferences()
            default_path = preferences.get("save_path", path)
            # This is a limitation - qBittorrent API doesn't provide free space info
            # We could potentially use os.statvfs or similar, but that's not client-specific
            return None
        except Exception as e:
            _L.error(f"Failed to get free space for {path}: {e}")
            return None

    @override
    def start_torrent(self, torrent_ids: list[str]) -> None:
        try:
            client = self._get_client()
            client.torrents_resume(torrent_hashes=torrent_ids)
        except Exception as e:
            _L.error(f"Failed to start torrents {torrent_ids}: {e}")

    @override
    def stop_torrent(self, torrent_ids: list[str]) -> None:
        try:
            client = self._get_client()
            client.torrents_pause(torrent_hashes=torrent_ids)
        except Exception as e:
            _L.error(f"Failed to stop torrents {torrent_ids}: {e}")

    def _convert_torrent(self, torrent: TorrentDictionary) -> TorrentInfo:
        """Convert qBittorrent TorrentDictionary to common TorrentInfo"""
        # Get torrent files
        try:
            files = torrent.files
            torrent_files = [
                TorrentFile(
                    name=file.name,
                    size=file.size,
                    selected=file.priority != 0,  # 0 means do not download
                )
                for file in files
            ]
        except Exception:
            # If we can't get files, create an empty list
            torrent_files = []

        # Map qBittorrent state to common status
        status = self._map_status(torrent.state)

        return TorrentInfo(
            id=torrent.hash,
            name=torrent.name,
            status=status,
            download_dir=torrent.save_path,
            downloaded_ever=torrent.completed,
            left_until_done=torrent.size - torrent.completed,
            files=torrent_files,
        )

    def _map_status(self, qbittorrent_state: str) -> str:
        """Map qBittorrent state to common status string"""
        # qBittorrent states: downloading, seeding, completed, paused, queued, etc.
        state_mapping = {
            "downloading": "downloading",
            "seeding": "seeding",
            "completed": "completed",
            "pausedDL": "paused",
            "pausedUP": "paused",
            "queuedDL": "queued",
            "queuedUP": "queued",
            "stalledDL": "stalled",
            "stalledUP": "stalled",
            "checkingDL": "checking",
            "checkingUP": "checking",
            "checkingResumeData": "checking",
            "moving": "moving",
            "unknown": "unknown",
            "missingFiles": "missing",
            "error": "error",
        }
        return state_mapping.get(qbittorrent_state, "unknown")
