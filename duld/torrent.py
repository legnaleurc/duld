import asyncio
from logging import getLogger
import os.path
from pathlib import PurePath

from transmission_rpc import Client, Torrent

from .drive import DriveUploader
from .settings import DiskSpaceData, TransmissionData


class DiskSpaceListener(object):
    def __init__(self, transmission: TransmissionData, disk_space: DiskSpaceData):
        self._transmission = transmission
        self._disk_space = disk_space
        self._timer = None

    async def __aenter__(self):
        self._timer = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, type_, exc, tb):
        assert self._timer
        self._timer.cancel()
        try:
            await self._timer
        except asyncio.CancelledError:
            getLogger(__name__).debug("stopped disk space listener")
        self._timer = None

    async def _loop(self):
        # check space every minute
        while True:
            await asyncio.sleep(60)
            self._check_space()

    def _check_space(self):
        torrent_client = connect_transmission(self._transmission)
        torrent_session = torrent_client.get_session()
        download_dir = torrent_session.download_dir
        free_space = torrent_client.free_space(download_dir)
        if free_space is None:
            return
        free_space_in_gb = free_space / 1024 / 1024 / 1024

        if free_space_in_gb >= self._disk_space.safe:
            if self._halted:
                getLogger(__name__).info(
                    f"resuming halted torrents: {free_space_in_gb}"
                )
                resume_halted_torrents(torrent_client)
                self._halted = False
            return
        if free_space_in_gb <= self._disk_space.danger:
            if not self._halted:
                getLogger(__name__).info(f"halting queued torrents: {free_space_in_gb}")
                halt_pending_torrents(torrent_client)
                self._halted = True
            return


async def upload_torrent(
    uploader: DriveUploader,
    upload_to: str,
    transmission: TransmissionData,
    torrent_id: int,
):
    torrent_client = connect_transmission(transmission)
    torrent = torrent_client.get_torrent(torrent_id)
    if not torrent:
        getLogger(__name__).warning(f"no such torrent id {torrent_id}")
        return
    torrent_name = torrent.name
    getLogger(__name__).info(f"{torrent_name}: processing")

    root_items = get_root_items(torrent)
    if not root_items:
        getLogger(__name__).warning(f"{torrent_name}: no item to upload?")
        return
    getLogger(__name__).debug(f"{torrent_name}: {root_items}")

    getLogger(__name__).info(f"{torrent_name}: begin uploading")
    torrent_root = torrent.download_dir
    if not torrent_root:
        getLogger(__name__).info(f"{torrent_name}: invalid location")
        return

    # upload files to Cloud Drive
    ok = False
    try:
        ok = await uploader.upload_torrent(
            PurePath(upload_to), torrent_id, torrent_root, root_items
        )
    except Exception:
        getLogger(__name__).exception("upload failed")
    if not ok:
        getLogger(__name__).info(f"{torrent_name}: upload failed")
        getLogger(__name__).info(f"retry url: /api/v1/torrents/{torrent_id}")
        return

    getLogger(__name__).info(f"{torrent_name}: remove torrent")
    # remove the task from Transmission first
    remove_torrent(torrent_client, torrent_id)


def get_completed(transmission: TransmissionData) -> list[Torrent]:
    torrent_client = connect_transmission(transmission)
    torrents = torrent_client.get_torrents()
    completed = filter(lambda t: t.left_until_done == 0, torrents)
    return list(completed)


def get_root_items(torrent: Torrent) -> list[str]:
    files = torrent.files()
    common: set[str] = set()

    # find common path
    for item in files:
        if not item.selected:
            continue
        parts = split_all(item.name)
        common.add(parts[0])

    return list(common)


def remove_torrent(client: Client, torrent_id: int) -> None:
    client.remove_torrent(torrent_id, delete_data=True)


def split_all(path: str) -> list[str]:
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


def connect_transmission(transmission: TransmissionData) -> Client:
    opt = transmission
    client = Client(
        host=opt.host,
        port=opt.port,
        username=opt.username,
        password=opt.password,
    )
    return client


def halt_pending_torrents(client: Client) -> None:
    torrents = client.get_torrents()
    torrent_id_list = [
        t.id for t in torrents if t.status == "downloading" and t.downloaded_ever == 0
    ]
    client.stop_torrent(torrent_id_list)


def resume_halted_torrents(client: Client) -> None:
    torrents = client.get_torrents()
    torrent_id_list = [
        t.id for t in torrents if t.status == "stopped" and t.downloaded_ever == 0
    ]
    client.start_torrent(torrent_id_list)
