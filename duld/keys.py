from aiohttp.web import AppKey

from .settings import Data
from .drive import DriveUploader


CONTEXT = AppKey("CONTEXT", Data)
UPLOADER = AppKey("UPLOADER", DriveUploader)
