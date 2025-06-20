from contextlib import contextmanager
from functools import partial
from logging import getLogger
from pathlib import Path
from tempfile import TemporaryDirectory

from .lib import compress_to_path


_L = getLogger(__name__)


@contextmanager
def compress_context():
    with TemporaryDirectory() as tmp:
        work_path = Path(tmp)
        yield partial(_compress_avif, work_path=work_path)


async def _compress_avif(src_path: Path, /, *, work_path: Path) -> Path:
    if not src_path.is_dir():
        return src_path
    if not src_path.name.endswith("[AVIF][DL版]"):
        return src_path
    _L.info(f"compressing {src_path}")
    compressed_path = await compress_to_path(src_path, work_path)
    _L.info(f"compressed {compressed_path}")
    return compressed_path
