import transmissionrpc

from . import acd
from . import settings
from .log import DEBUG, INFO, WARNING, EXCEPTION


async def process_torrent(torrent_id):
    torrent_client = connect_transmission()
    torrent = torrent_client.get_torrent(torrent_id)
    if not torrent:
        WARNING('tmacd') << 'no such torrent id {0}'.format(torrent_id)
        return
    torrent_name = torrent.name
    INFO('tmacd') << 'processing {0}'.format(torrent_name)

    root_items = get_root_items(torrent)
    if not root_items:
        WARNING('tmacd') << 'no item to upload?'
        return
    DEBUG('tmacd') << 'root times: {0}'.format(root_items)

    INFO('tmacd') << 'begin uploading'
    torrent_root = torrent.downloadDir
    # upload files to Amazon Cloud Drive
    try:
        await acd.upload(torrent_root, root_items)
    except Exception as e:
        EXCEPTION('tmacd') << 'upload {0} failed'.format(torrent_name)
        INFO('tmacd') << 'retry url: /torrents/{0}'.format(torrend_id)
        return

    INFO('tmacd') << 'remove torrent'
    # remove the task from Transmission first
    remove_torrent(torrent_client, torrent_id)


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
        parts = os.path.split(path)
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
