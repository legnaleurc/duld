import concurrent.futures as cf
from functools import partial as ftp
import hashlib
import json
import multiprocessing as mp
import os.path as op
import pathlib
import re
import threading

from tornado import locks as tl
import tornado.platform.asyncio as tpaio
import wcpan.drive.google as wdg
from wcpan.logger import DEBUG, INFO, ERROR, EXCEPTION, WARNING
import wcpan.worker as ww

from . import settings


def off_main_thread(fn):
    @ft.wraps(fn)
    def wrapper(self, *args, **kwargs):
        future = self._pool.submit(fn, self, *args, **kwargs)
        # NOTE dirty hack
        future = tpaio.to_tornado_future(future)
        return future
    return wrapper


class DriveUploader(object):

    def __init__(self):
        self._drive = wdg.Drive(op.expanduser('~/.cache/wcpan/drive/google'))
        self._sync_lock = tl.Lock()
        self._queue = ww.AsyncQueue(8)
        self._pool = cf.ThreadPoolExecutor(max_workers=mp.cpu_count())

    def initialize(self):
        self._drive.initialize()
        self._queue.start()

    async def close(self):
        self._pool.shutdown()
        await self._queue.stop()
        self._drive.close()

    async def upload_path(self, remote_path, local_path):
        async with self._sync_lock:
            ok = await self._drive.sync()
            if not ok:
                return False

        node = await self._drive.get_node_by_path(remote_path)
        if not node:
            ERROR('duld') << remote_path << 'not found'
            return False

        local_path = pathlib.Path(local_path)
        ok = await self._upload(node, local_path)
        if not ok:
            ERROR('duld') << item << 'upload failed'
        return ok

    async def upload_torrent(self, remote_path, torrent_root, root_items):
        async with self._sync_lock:
            ok = await self._drive.sync()
            if not ok:
                return False

        node = await self._drive.get_node_by_path(remote_path)
        if not node:
            ERROR('duld') << remote_path << 'not found'
            return False

        # files/directories to be upload
        items = map(lambda _: pathlib.Path(torrent_root, _), root_items)
        all_ok = True
        for item in items:
            ok = await self._upload(node, item)
            if not ok:
                ERROR('duld') << item << 'upload failed'
                all_ok = False
                continue

        return all_ok

    async def _upload(self, node, local_path):
        if should_exclude(local_path.name):
            INFO('duld') << 'excluded' << local_path
            return True

        if local_path.is_dir():
            ok = await self._upload_directory(node, local_path)
        else:
            ok = await self._upload_file_retry(node, local_path)
        return ok

    async def _upload_directory(self, node, local_path):
        dir_name = local_path.name

        # find or create remote directory
        child_node = await self._drive.get_child(node, dir_name)
        if child_node and child_node.is_file:
            # is file
            path = await self._drive.get_path(child_node)
            ERROR('duld') << '(remote)' << path << 'is a file'
            return False
        elif not child_node or not child_node.is_available or not node.is_available:
            # not exists
            child_node = await self._drive.create_folder(dir_name, node)
            if not child_node:
                path = await self._drive.get_path(node)
                path = op.join(path, dir_name)
                ERROR('duld') << '(remote) cannot create' << path
                return False

        all_ok = True
        for child_path in local_path.iterdir():
            ok = await self._upload(child_node, child_path)
            if not ok:
                ERROR('duld') << '(remote) cannot upload' << child_path
                all_ok = False

        return all_ok

    async def _upload_file_retry(self, node, local_path):
        while True:
            try:
                ok = await self._upload_file(node, local_path)
            except wdg.UploadConflictedError as e:
                ok = await self._try_resolve_name_confliction(e.node)
                if not ok:
                    ERROR('duld') << 'cannot resolve conclict for {0}, remote id: {1}'.format(local_path, e.node.id_)
                    return False
            except Exception as e:
                WARNING('duld') << 'retry because' << str(e)
            else:
                return ok

            async with self._sync_lock:
                ok = await self._drive.sync()
                if not ok:
                    ERROR('duld') << 'sync failed'
                    return False

    async def _upload_file(self, node, local_path):
        file_name = local_path.name
        remote_path = await self._drive.get_path(node)
        remote_path = pathlib.Path(remote_path, file_name)

        child_node = await self._drive.get_child(node, file_name)

        if child_node and child_node.is_available:
            if child_node.is_folder:
                ERROR('duld') << '(remote)' << remote_path << 'is a directory'
                return False

            # check integrity
            ok = await self._verify_remote_file(local_path, remote_path, child_node.md5)
            if not ok:
                return False
            INFO('duld') << remote_path << 'already exists'

        if not child_node or not child_node.is_available:
            INFO('duld') << 'uploading' << remote_path

            child_node = await self._drive.upload_file(str(local_path), node)

            # check integrity
            ok = await self._verify_remote_file(local_path, remote_path, child_node.md5)
            if not ok:
                return False

        return True

    @off_main_thread
    def _verify_remote_file(self, local_path, remote_path, remote_md5):
        local_md5 = md5sum(local_path)
        if local_md5 != remote_md5:
            ERROR('duld') << '(remote)' << remote_path << 'has a different md5 ({0}, {1})'.format(local_md5, remote_md5)
            return False
        return True

    # used in exception handler, DO NOT throw another exception again
    async def _try_resolve_name_confliction(self, node):
        try:
            ok = await self._drive.trash_node_by_id(node.id_)
            return ok
        except Exception as e:
            EXCEPTION('duld', e)
        return False


def md5sum(path):
    assert threading.current_thread() is not threading.main_thread()
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
