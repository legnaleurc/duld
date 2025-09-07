from asyncio import TaskGroup

from aiohttp.web import AppKey

from .drive import DriveUploader
from .settings import Data
from .torrent import TorrentClientRegistry


CONTEXT = AppKey("CONTEXT", Data)
UPLOADER = AppKey("UPLOADER", DriveUploader)
SCHEDULER = AppKey("SCHEDULER", TaskGroup)
TORRENT_REGISTRY = AppKey("TORRENT_REGISTRY", TorrentClientRegistry)
