import asyncio
import asyncio.subprocess
import os
import subprocess

from . import settings
from .log import DEBUG, INFO


async def upload(torrent_root, root_items):
    # sync local cache first
    # TODO global lock: this opration is not reentrant
    cmd = ['acdcli', '--verbose', 'sync']
    # call the external process
    exit_code = await call_acdcli(cmd)

    cmd = ['acdcli', '--verbose', 'upload', '--max-retries', '4']
    # exclude pattern
    exclude = settings['exclude_pattern']
    for p in exclude:
        cmd.extend(('--exclude-regex', p))
    # files/directories to be upload
    items = map(lambda _: os.path.join(torrent_root, _), root_items)
    cmd.extend(items)
    # upload destination
    cmd.append(settings['upload_to'])
    DEBUG('tmacd') << 'acdcli command: {0}'.format(cmd)

    # call the external process
    exit_code = await call_acdcli(cmd)
    return exit_code


async def call_acdcli(cmd):
    p = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL,
                                             stderr=asyncio.subprocess.PIPE)
    # tee log
    while True:
        line = await p.stderr.readline()
        if not line:
            break
        INFO('acd') << line.decode('utf-8').strip()
    exit_code = await p.wait()
    return exit_code
