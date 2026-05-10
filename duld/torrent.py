import asyncio
import logging
import os.path

from transmission_rpc import Client, Torrent, TransmissionError

from .settings import DiskSpaceData, TransmissionData
from .upload import Uploader


_L = logging.getLogger(__name__)


async def upload_by_id(
    *,
    uploader: Uploader,
    transmission: TransmissionData,
    torrent_id: int,
) -> None:
    try:
        torrent_client = _connect_transmission(transmission)
    except Exception as e:
        _L.error(f"transmission error: {e}")
        return

    torrent = torrent_client.get_torrent(torrent_id)
    if not torrent:
        _L.warning(f"no such torrent id {torrent_id}")
        return

    root_items = _get_root_items(torrent)
    if not root_items:
        _L.warning(f"{torrent.name}: no item to upload?")
        return
    _L.debug(f"{torrent.name}: {root_items}")

    torrent_root = _get_root_dir(torrent, transmission.download_dir)
    if not torrent_root:
        _L.error(f"{torrent.name}: invalid location")
        return

    # upload files to Cloud Drive
    try:
        await uploader.upload_from_torrent(torrent_id, torrent_root, root_items)
    except Exception:
        _L.exception("upload failed")
        _L.error(f"retry url: /api/v1/torrents/{torrent_id}")
        return

    # remove the task from Transmission first
    _remove_torrent(torrent_client, torrent)


def get_completed(transmission: TransmissionData) -> list[Torrent]:
    torrent_client = _connect_transmission(transmission)
    torrents = torrent_client.get_torrents()
    completed = filter(lambda t: t.left_until_done == 0, torrents)
    return list(completed)


async def add_urls(
    urls: list[str],
    *,
    transmission: TransmissionData,
) -> dict[str, Torrent | None]:
    torrent_client = _connect_transmission(transmission)

    torrent_dict: dict[str, Torrent | None] = {}
    for url in urls:
        try:
            torrent = torrent_client.add_torrent(url, paused=True)
            torrent_dict[url] = torrent
        except Exception as e:
            _L.error(f"failed to add torrent {url}: {e}")
            torrent_dict[url] = None

    return torrent_dict


def _get_root_items(torrent: Torrent) -> list[str]:
    files = torrent.get_files()
    common: set[str] = set()

    # find common path
    for item in files:
        if not item.selected:
            continue
        parts = _split_all(item.name)
        common.add(parts[0])

    return list(common)


def _get_root_dir(torrent: Torrent, download_dir: str | None) -> str | None:
    if download_dir:
        return download_dir
    return torrent.download_dir


def _remove_torrent(client: Client, torrent: Torrent) -> None:
    client.remove_torrent(torrent.id, delete_data=True)
    _L.info(f"{torrent.name}: remove torrent")


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


def _connect_transmission(transmission: TransmissionData) -> Client:
    opt = transmission
    client = Client(
        host=opt.host,
        port=opt.port,
        username=opt.username,
        password=opt.password,
    )
    return client


async def watch_disk_space(
    *, transmission: TransmissionData, disk_space: DiskSpaceData
):
    halted_ids: list[int] = []
    while True:
        await asyncio.sleep(60)
        try:
            halted_ids = _check_disk_space(transmission, disk_space, halted_ids)
        except TransmissionError as e:
            _L.error(f"transmission error {e}. data: {transmission}")
        except Exception:
            _L.exception("cannot check disk space")


def _check_disk_space(
    transmission: TransmissionData, disk_space: DiskSpaceData, halted_ids: list[int]
) -> list[int]:
    if disk_space.safe <= disk_space.danger:
        raise ValueError("invalid disk space range")

    torrent_client = _connect_transmission(transmission)
    torrent_session = torrent_client.get_session()
    download_dir = torrent_session.download_dir
    free_space = torrent_client.free_space(download_dir)
    if free_space is None:
        _L.warning("cannot get free space")
        return halted_ids
    free_space_in_gb = free_space / 1024 / 1024 / 1024

    if free_space_in_gb >= disk_space.safe:
        if halted_ids:
            _L.info(f"resuming halted torrents: {free_space_in_gb}")
            _resume_halted_torrents(torrent_client, halted_ids)
        return []

    if free_space_in_gb <= disk_space.danger:
        if not halted_ids:
            _L.info(f"halting queued torrents: {free_space_in_gb}")
            halted_ids = _halt_pending_torrents(torrent_client)
        return halted_ids

    return halted_ids


def _halt_pending_torrents(client: Client) -> list[int]:
    torrents = client.get_torrents()
    torrent_id_list = [
        t.id for t in torrents if t.status == "downloading" and t.downloaded_ever == 0
    ]
    if torrent_id_list:
        client.stop_torrent(torrent_id_list)  # type: ignore
    return torrent_id_list


def _resume_halted_torrents(client: Client, torrent_id_list: list[int]) -> None:
    if torrent_id_list:
        client.start_torrent(torrent_id_list)  # type: ignore
