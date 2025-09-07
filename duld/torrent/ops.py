import asyncio
import logging
import os.path
from pathlib import PurePath

from ..drive import DriveUploader
from ..settings import DiskSpaceData
from .client import TorrentClient, TorrentInfo
from .registry import TorrentClientRegistry


_L = logging.getLogger(__name__)


async def upload_by_id(
    *,
    uploader: DriveUploader,
    upload_to: PurePath,
    torrent_client: TorrentClient,
    torrent_id: str,
) -> None:
    """Upload a torrent by ID using the specified torrent client"""
    torrent = torrent_client.get_torrent(torrent_id)
    if not torrent:
        _L.warning(f"no such torrent id {torrent_id}")
        return

    root_items = _get_root_items(torrent)
    if not root_items:
        _L.warning(f"{torrent.name}: no item to upload?")
        return
    _L.debug(f"{torrent.name}: {root_items}")

    torrent_root = _get_root_dir(torrent, torrent_client.config)
    if not torrent_root:
        _L.error(f"{torrent.name}: invalid location")
        return

    # upload files to Cloud Drive
    try:
        await uploader.upload_from_torrent(
            upload_to, torrent_id, torrent_root, root_items
        )
    except Exception:
        _L.exception("upload failed")
        _L.error(f"retry url: /api/v1/torrents/{torrent_id}")
        return

    # remove the task from torrent client
    torrent_client.remove_torrent(torrent_id, delete_data=True)


def get_completed(torrent_client: TorrentClient) -> list[TorrentInfo]:
    """Get all completed torrents from the specified client"""
    torrents = torrent_client.get_torrents()
    completed = filter(lambda t: t.left_until_done == 0, torrents)
    return list(completed)


async def add_urls(
    urls: list[str],
    *,
    torrent_client: TorrentClient,
) -> dict[str, TorrentInfo | None]:
    """Add torrent URLs to the specified client"""
    torrent_dict: dict[str, TorrentInfo | None] = {}
    for url in urls:
        try:
            torrent = torrent_client.add_torrent(url, paused=True)
            torrent_dict[url] = torrent
        except Exception as e:
            _L.error(f"failed to add torrent {url}: {e}")
            torrent_dict[url] = None

    return torrent_dict


def _get_root_items(torrent: TorrentInfo) -> list[str]:
    """Get root items from torrent files"""
    common: set[str] = set()

    # find common path
    for file in torrent.files:
        if not file.selected:
            continue
        parts = _split_all(file.name)
        common.add(parts[0])

    return list(common)


def _get_root_dir(torrent: TorrentInfo, config) -> str | None:
    """Get the root directory for the torrent"""
    if hasattr(config, "download_dir") and config.download_dir:
        return config.download_dir
    return torrent.download_dir


def _split_all(path: str) -> list[str]:
    """
    Returns path parts by directories.
    """
    allparts: list[str] = []
    while True:
        parts = os.path.split(path)
        if parts[0] == path:  # sentinel for absolute paths
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path:  # sentinel for relative paths
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts


async def watch_disk_space(
    *, torrent_registry: TorrentClientRegistry, disk_space: DiskSpaceData
):
    """Watch disk space for all torrent clients"""
    halted = False
    while True:
        await asyncio.sleep(60)
        try:
            halted = _check_disk_space(torrent_registry, disk_space, halted)
        except Exception:
            _L.exception("cannot check disk space")


def _check_disk_space(
    torrent_registry: TorrentClientRegistry, disk_space: DiskSpaceData, halted: bool
) -> bool:
    """Check disk space for all clients and manage torrent states"""
    if disk_space.safe <= disk_space.danger:
        raise ValueError("invalid disk space range")

    clients = torrent_registry.get_all_clients()
    if not clients:
        return halted

    # Check the first client's disk space (assuming they all use the same storage)
    client = next(iter(clients.values()))
    session = client.get_session()
    download_dir = session.download_dir
    free_space = client.free_space(download_dir)
    if free_space is None:
        _L.warning("cannot get free space")
        return halted
    free_space_in_gb = free_space / 1024 / 1024 / 1024

    if free_space_in_gb >= disk_space.safe:
        if halted:
            _L.info(f"resuming halted torrents: {free_space_in_gb}")
            _resume_halted_torrents(torrent_registry)
        return False

    if free_space_in_gb <= disk_space.danger:
        if not halted:
            _L.info(f"halting queued torrents: {free_space_in_gb}")
            _halt_pending_torrents(torrent_registry)
        return True

    return halted


def _halt_pending_torrents(torrent_registry: TorrentClientRegistry) -> None:
    """Halt pending torrents across all clients"""
    clients = torrent_registry.get_all_clients()
    for client in clients.values():
        torrents = client.get_torrents()
        torrent_id_list = [
            t.id
            for t in torrents
            if t.status == "downloading" and t.downloaded_ever == 0
        ]
        if torrent_id_list:
            client.stop_torrent(torrent_id_list)


def _resume_halted_torrents(torrent_registry: TorrentClientRegistry) -> None:
    """Resume halted torrents across all clients"""
    clients = torrent_registry.get_all_clients()
    for client in clients.values():
        torrents = client.get_torrents()
        torrent_id_list = [
            t.id for t in torrents if t.status == "stopped" and t.downloaded_ever == 0
        ]
        if torrent_id_list:
            client.start_torrent(torrent_id_list)
