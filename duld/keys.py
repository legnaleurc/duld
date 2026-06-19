from asyncio import TaskGroup

from aiohttp.web import AppKey

from .filters import FilterStore
from .settings import Data
from .tasks import UploadTaskManager
from .upload import Uploader


CONTEXT = AppKey("CONTEXT", Data)
FILTER_STORE = AppKey("FILTER_STORE", FilterStore)
UPLOADER = AppKey("UPLOADER", Uploader)
SCHEDULER = AppKey("SCHEDULER", TaskGroup)
TASK_MANAGER = AppKey("TASK_MANAGER", UploadTaskManager)
