import asyncio
import concurrent.futures as cf
import contextlib as cl
import functools as ft
import hashlib
import json
import multiprocessing as mp
import os.path as op
import pathlib
import re
import threading

import aiohttp
import wcpan.drive.google as wdg
from wcpan.logger import DEBUG, INFO, ERROR, EXCEPTION, WARNING
import wcpan.worker as ww

from . import settings


class DriveUploader(object):

    def __init__(self):
        self._sync_lock = asyncio.Lock()
        self._drive = None
        self._curl = None
        self._queue = None
        self._pool = None
        self._raii = None

    async def __aenter__(self):
        async with cl.AsyncExitStack() as stack:
            self._drive = await stack.enter_async_context(wdg.Drive())
            self._queue = await stack.enter_async_context(ww.AsyncQueue(8))
            self._curl = await stack.enter_async_context(aiohttp.ClientSession())
            self._pool = stack.enter_context(cf.ProcessPoolExecutor())
            self._raii = stack.pop_all()
        return self

    async def __aexit__(self, type_, exc, tb):
        await self._raii.aclose()
        self._drive = None
        self._curl = None
        self._queue = None
        self._pool = None
        self._raii = None

    async def upload_path(self, remote_path, local_path):
        await self._sync()

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
        await self._sync()

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

    async def _sync(self):
        async with self._sync_lock:
            count = 0
            async for changes in self._drive.sync():
                count += 1
            INFO('duld') << 'sync' << count

    async def _upload(self, node, local_path):
        if await self._should_exclude(local_path.name):
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
        child_node = await self._drive.get_node_by_name_from_parent(dir_name, node)
        if child_node and child_node.is_file:
            # is file
            path = await self._drive.get_path(child_node)
            ERROR('duld') << '(remote)' << path << 'is a file'
            return False
        elif not child_node or child_node.trashed or node.trashed:
            # not exists
            child_node = await self._drive.create_folder(node, dir_name)
            if not child_node:
                path = await self._drive.get_path(node)
                path = op.join(path, dir_name)
                ERROR('duld') << '(remote) cannot create' << path
                return False

            # Need to update local cache for the added folder.
            # In theory we should pass remote path instead of doing this.
            async with self._sync_lock:
                async for changes in self._drive.sync():
                    INFO('duld') << 'sync' << len(changes)

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
            except wdg.UploadError as e:
                ok = await self._try_resolve_name_confliction(node, local_path)
                if not ok:
                    ERROR('duld') << 'cannot resolve conclict for {0}'.format(local_path)
                    return False
                EXCEPTION('duld', e) << 'retry upload file'
            except Exception as e:
                EXCEPTION('duld', e) << 'retry upload file'
            else:
                return ok

            async with self._sync_lock:
                async for changes in self._drive.sync():
                    INFO('duld') << 'sync' << len(changes)

    async def _upload_file(self, node, local_path):
        file_name = local_path.name
        remote_path = await self._drive.get_path(node)
        remote_path = pathlib.Path(remote_path, file_name)

        child_node = await self._drive.get_node_by_name_from_parent(file_name, node)

        if child_node and not child_node.trashed:
            if child_node.is_folder:
                ERROR('duld') << '(remote)' << remote_path << 'is a directory'
                return False

            # check integrity
            ok = await self._verify_remote_file(local_path, remote_path, child_node.md5)
            if not ok:
                return False
            INFO('duld') << remote_path << 'already exists'

        if not child_node or child_node.trashed:
            INFO('duld') << 'uploading' << remote_path

            child_node = await wdg.upload_from_local(self._drive, node, str(local_path))

            # check integrity
            ok = await self._verify_remote_file(local_path, remote_path, child_node.md5)
            if not ok:
                return False

        return True

    async def _verify_remote_file(self, local_path, remote_path, remote_md5):
        loop = asyncio.get_running_loop()
        local_md5 = await loop.run_in_executor(self._pool, md5sum, local_path)
        if local_md5 != remote_md5:
            ERROR('duld') << '(remote)' << remote_path << 'has a different md5 ({0}, {1})'.format(local_md5, remote_md5)
            return False
        return True

    # used in exception handler, DO NOT throw another exception again
    async def _try_resolve_name_confliction(self, node, local_path):
        name = op.basename(local_path)
        node = await self._drive.get_node_by_name_from_parent(name, node)
        if not node:
            return True
        try:
            ok = await self._drive.trash_node_by_id(node.id_)
            return ok
        except Exception as e:
            EXCEPTION('duld', e)
        return False

    async def _should_exclude(self, name):
        for pattern in settings['exclude_pattern']:
            if re.match(pattern, name, re.IGNORECASE):
                return True

        if settings['exclude_url']:
            async with self._curl.get(settings['exclude_url']) as rv:
                rv = await rv.json()
                for _, pattern in rv.items():
                    if re.match(pattern, name, re.IGNORECASE):
                        return True

        return False


def md5sum(path):
    hasher = hashlib.md5()
    with path.open('rb') as fin:
        while True:
            chunk = fin.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
