from asyncio import TaskGroup

from aiohttp.web import AppKey

from .filters import FilterStore
from .settings import Data
from .upload import Uploader


CONTEXT = AppKey("CONTEXT", Data)
FILTER_STORE = AppKey("FILTER_STORE", FilterStore)
UPLOADER = AppKey("UPLOADER", Uploader)
SCHEDULER = AppKey("SCHEDULER", TaskGroup)
