import asyncio
import os
import os.path as op

import transmissionrpc
from wcpan.logger import DEBUG, INFO, WARNING, EXCEPTION

from . import settings


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
        torrent_session = torrent_client.session_stats()
        free_space_in_gb = torrent_session.download_dir_free_space / 1024 / 1024 / 1024

        reserved_space_in_gb = settings['reserved_space_in_gb']

        if free_space_in_gb >= reserved_space_in_gb['safe']:
            if self._halted:
                INFO('acdul') << 'resuming halted torrents: {0}'.format(free_space_in_gb)
                resume_halted_torrents(torrent_client)
                self._halted = False
            return
        if free_space_in_gb <= reserved_space_in_gb['danger']:
            if not self._halted:
                INFO('acdul') << 'halting queued torrents: {0}'.format(free_space_in_gb)
                halt_pending_torrents(torrent_client)
                self._halted = True
            return


async def upload_torrent(uploader, torrent_id):
    torrent_client = connect_transmission()
    torrent = torrent_client.get_torrent(torrent_id)
    if not torrent:
        WARNING('duld') << 'no such torrent id {0}'.format(torrent_id)
        return
    torrent_name = torrent.name
    INFO('duld') << '{0}: processing'.format(torrent_name)

    root_items = get_root_items(torrent)
    if not root_items:
        WARNING('duld') << '{0}: no item to upload?'.format(torrent_name)
        return
    DEBUG('duld') << '{0}: {1}'.format(torrent_name, root_items)

    INFO('duld') << '{0}: begin uploading'.format(torrent_name)
    torrent_root = torrent.downloadDir
    # upload files to Cloud Drive
    ok = False
    try:
        ok = await uploader.upload_torrent(settings['upload_to'], torrent_root, root_items)
    except Exception as e:
        EXCEPTION('duld', e)
    if not ok:
        INFO('duld') << '{0}: upload failed'.format(torrent_name)
        INFO('duld') << 'retry url: /api/v1/torrents/{0}'.format(torrent_id)
        return

    INFO('duld') << '{0}: remove torrent'.format(torrent_name)
    # remove the task from Transmission first
    remove_torrent(torrent_client, torrent_id)


def get_completed():
    torrent_client = connect_transmission()
    completed = filter(lambda _: _.leftUntilDone == 0, torrent_client.get_torrents())
    return list(completed)


def get_root_items(torrent):
    files = torrent.files()
    common = set()

    # find common path
    for fid, item in files.items():
        if not item['selected']:
            continue
        parts = split_all(item['name'])
        common.add(parts[0])

    common = list(common)
    return common


def remove_torrent(client, torrent_id):
    client.remove_torrent(torrent_id, delete_data=True)


def split_all(path):
    '''
    Returns path parts by directories.
    '''
    allparts = []
    while True:
        parts = op.split(path)
        if parts[0] == path:  # sentinel for absolute paths
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path: # sentinel for relative paths
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts


def connect_transmission():
    opt = settings['transmission']
    client = transmissionrpc.Client(opt['host'], port=opt['port'],
                                    user=opt.get('username', None),
                                    password=opt.get('password', None))
    return client


def halt_pending_torrents(client):
    torrents = client.get_torrents()
    torrents = filter(lambda t: t.status == 'downloading' and t.downloadedEver == 0, torrents)
    for t in torrents:
        t.stop()


def resume_halted_torrents(client):
    torrents = client.get_torrents()
    torrents = filter(lambda t: t.status == 'stopped' and t.downloadedEver == 0, torrents)
    for t in torrents:
        t.start()
