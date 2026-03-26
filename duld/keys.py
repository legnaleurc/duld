from asyncio import TaskGroup

from aiohttp.web import AppKey

from .settings import Data
from .upload import Uploader


CONTEXT = AppKey("CONTEXT", Data)
UPLOADER = AppKey("UPLOADER", Uploader)
SCHEDULER = AppKey("SCHEDULER", TaskGroup)
