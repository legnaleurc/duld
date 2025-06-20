from asyncio import TaskGroup

from aiohttp.web import AppKey

from .drive import DriveUploader
from .settings import Data


CONTEXT = AppKey("CONTEXT", Data)
UPLOADER = AppKey("UPLOADER", DriveUploader)
SCHEDULER = AppKey("SCHEDULER", TaskGroup)
