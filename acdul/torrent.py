import os.path as op

import transmissionrpc
from wcpan.logger import DEBUG, INFO, WARNING, EXCEPTION

from . import settings


async def upload_torrent(uploader, torrent_id):
    torrent_client = connect_transmission()
    torrent = torrent_client.get_torrent(torrent_id)
    if not torrent:
        WARNING('acdul') << 'no such torrent id {0}'.format(torrent_id)
        return
    torrent_name = torrent.name
    INFO('acdul') << '{0}: processing'.format(torrent_name)

    root_items = get_root_items(torrent)
    if not root_items:
        WARNING('acdul') << '{0}: no item to upload?'.format(torrent_name)
        return
    DEBUG('acdul') << '{0}: {1}'.format(torrent_name, root_items)

    INFO('acdul') << '{0}: begin uploading'.format(torrent_name)
    torrent_root = torrent.downloadDir
    # upload files to Amazon Cloud Drive
    try:
        await uploader.upload_torrent(settings['upload_to'], torrent_root, root_items)
    except Exception as e:
        EXCEPTION('acdul') << '{0}: upload failed'.format(torrent_name)
        INFO('acdul') << 'retry url: /torrents/{0}'.format(torrent_id)
        return

    INFO('acdul') << '{0}: remove torrent'.format(torrent_name)
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
                                    user=opt['username'],
                                    password=opt['password'])
    return client