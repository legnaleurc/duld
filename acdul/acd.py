import hashlib
import os.path as op
import pathlib
import re

from tornado import locks as tl
from wcpan.acd import ACDController
from wcpan.logger import DEBUG, INFO, ERROR, EXCEPTION, WARNING

from . import settings


class ACDUploader(object):

    def __init__(self):
        self._acd = ACDController(op.expanduser('~/.cache/acd_cli'))
        self._sync_lock = tl.Lock()

    def close(self):
        self._acd.close()

    async def upload_path(self, remote_path, local_path):
        async with self._sync_lock:
            ok = await self._acd.sync()
            if not ok:
                return False

        node = await self._acd.resolve_path(remote_path)
        if not node:
            ERROR('acdul') << remote_path << 'not found'
            return False

        local_path = pathlib.Path(local_path)
        ok = await self._upload(node, local_path)
        if not ok:
            ERROR('acdul') << item << 'upload failed'
        return ok

    async def upload_torrent(self, remote_path, torrent_root, root_items):
        async with self._sync_lock:
            ok = await self._acd.sync()
            if not ok:
                return False

        node = await self._acd.resolve_path(remote_path)
        if not node:
            ERROR('acdul') << remote_path << 'not found'
            return False

        # files/directories to be upload
        items = map(lambda _: pathlib.Path(torrent_root, _), root_items)
        all_ok = True
        for item in items:
            ok = await self._upload(node, item)
            if not ok:
                ERROR('acdul') << item << 'upload failed'
                all_ok = False
                continue

        return all_ok

    async def _upload(self, node, local_path):
        if should_exclude(local_path.name):
            INFO('acdul') << 'excluded' << local_path
            return True

        if local_path.is_dir():
            ok = await self._upload_directory(node, local_path)
        else:
            ok = await self._upload_file(node, local_path)
        return ok

    async def _upload_directory(self, node, local_path):
        dir_name = local_path.name

        # find or create remote directory
        child_node = await self._acd.get_child(node, dir_name)
        if child_node and child_node.is_file:
            # is file
            path = await self._acd.resolve_path(child_node)
            ERROR('acdul') << '(remote)' << path << 'is a file'
            return False
        elif not child_node or not child_node.is_available or not node.is_available:
            # not exists
            child_node = await self._acd.create_directory(node, dir_name)
            if not child_node:
                path = await self._acd.resolve_path(node)
                path = op.join(path, dir_name)
                ERROR('acdul') << '(remote) cannot create' << path
                return False

        all_ok = True
        for child_path in local_path.iterdir():
            ok = await self._upload(child_node, child_path)
            if not ok:
                ERROR('acdul') << '(remote) cannot upload' << child_path
                all_ok = False

        return all_ok

    async def _upload_file_retry(self, node, local_path):
        while True:
            try:
                ok = await self._upload_file(self, node, local_path)
                return ok
            except Exception as e:
                WARNING('acdul') << 'retry because' << str(e)

            async with self._sync_lock:
                ok = await self._acd.sync()
                if not ok:
                    ERROR('acdul') << 'sync failed'
                    return False

    async def _upload_file(self, node, local_path):
        file_name = local_path.name
        remote_path = await self._acd.get_path(node)
        remote_path = pathlib.Path(remote_path, file_name)

        child_node = await self._acd.get_child(node, file_name)

        if child_node and child_node.is_available:
            if child_node.is_folder:
                ERROR('acdul') << '(remote)' << remote_path << 'is a directory'
                return False

            # check integrity
            ok = verify_remote_file(local_path, remote_path, child_node)
            if not ok:
                return False
            INFO('acdul') << remote_path << 'already exists'

        if not child_node or not child_node.is_available:
            INFO('acdul') << 'uploading' << remote_path

            child_node = await self._acd.upload_file(node, str(local_path))

            # check integrity
            ok = verify_remote_file(local_path, remote_path, child_node)
            if not ok:
                return False

        return True


def verify_remote_file(local_path, remote_path, node):
    local_md5 = md5sum(local_path)
    remote_md5 = node.md5
    if local_md5 != remote_md5:
        ERROR('acdul') << '(remote)' << remote_path << 'has a different md5 ({0}, {1})'.format(local_md5, remote_md5)
        return False
    return True


def md5sum(path):
    hasher = hashlib.md5()
    with path.open('rb') as fin:
        while True:
            chunk = fin.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def should_exclude(name):
    for pattern in settings['exclude_pattern']:
        if re.match(pattern, name, re.IGNORECASE):
            return True
    return False
