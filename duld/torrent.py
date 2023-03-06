import asyncio
import os.path

from transmission_rpc import Client, Torrent
from wcpan.logger import DEBUG, INFO, WARNING, EXCEPTION

from . import settings
from .drive import DriveUploader


class DiskSpaceListener(object):
    def __init__(self):
        self._timer = None

    def __enter__(self):
        self._timer = asyncio.create_task(self._loop())
        return self

    def __exit__(self, type_, exc, tb):
        self._timer.cancel()
        self._timer = None

    async def _loop(self):
        # check space every minute
        while True:
            await asyncio.sleep(60)
            self._check_space()

    def _check_space(self):
        torrent_client = connect_transmission()
        torrent_session = torrent_client.get_session()
        download_dir = torrent_session.download_dir
        free_space_in_gb = torrent_client.free_space(download_dir) / 1024 / 1024 / 1024

        reserved_space_in_gb = settings["reserved_space_in_gb"]

        if free_space_in_gb >= reserved_space_in_gb["safe"]:
            if self._halted:
                INFO("acdul") << "resuming halted torrents: {0}".format(
                    free_space_in_gb
                )
                resume_halted_torrents(torrent_client)
                self._halted = False
            return
        if free_space_in_gb <= reserved_space_in_gb["danger"]:
            if not self._halted:
                INFO("acdul") << "halting queued torrents: {0}".format(free_space_in_gb)
                halt_pending_torrents(torrent_client)
                self._halted = True
            return


async def upload_torrent(uploader: DriveUploader, torrent_id: str):
    torrent_client = connect_transmission()
    torrent = torrent_client.get_torrent(torrent_id)
    if not torrent:
        WARNING("duld") << "no such torrent id {0}".format(torrent_id)
        return
    torrent_name = torrent.name
    INFO("duld") << "{0}: processing".format(torrent_name)

    root_items = get_root_items(torrent)
    if not root_items:
        WARNING("duld") << "{0}: no item to upload?".format(torrent_name)
        return
    DEBUG("duld") << "{0}: {1}".format(torrent_name, root_items)

    INFO("duld") << "{0}: begin uploading".format(torrent_name)
    torrent_root = torrent.download_dir
    if not torrent_root:
        INFO("duld") << "{0}: invalid location".format(torrent_name)
        return

    # upload files to Cloud Drive
    ok = False
    try:
        ok = await uploader.upload_torrent(
            settings["upload_to"], torrent_id, torrent_root, root_items
        )
    except Exception as e:
        EXCEPTION("duld", e)
    if not ok:
        INFO("duld") << "{0}: upload failed".format(torrent_name)
        INFO("duld") << "retry url: /api/v1/torrents/{0}".format(torrent_id)
        return

    INFO("duld") << "{0}: remove torrent".format(torrent_name)
    # remove the task from Transmission first
    remove_torrent(torrent_client, torrent_id)


def get_completed():
    torrent_client = connect_transmission()
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


def remove_torrent(client: Client, torrent_id: str) -> None:
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


def connect_transmission() -> Client:
    opt = settings["transmission"]
    client = Client(
        host=opt["host"],
        port=opt["port"],
        username=opt.get("username", None),
        password=opt.get("password", None),
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
