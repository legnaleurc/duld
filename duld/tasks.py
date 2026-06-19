import logging
from collections.abc import Awaitable, Callable, Coroutine, Hashable
from typing import Protocol


_L = logging.getLogger(__name__)

type JobKey = Hashable
type JobFactory = Callable[[], Awaitable[object]]


class TaskScheduler(Protocol):
    def create_task[T](self, coro: Coroutine[None, None, T]) -> object: ...


class UploadTaskManager:
    def __init__(self, scheduler: TaskScheduler) -> None:
        self._scheduler = scheduler
        self._active = set[JobKey]()

    def create[T](self, coro: Coroutine[None, None, T]) -> object:
        return self._scheduler.create_task(coro)

    def create_once(self, key: JobKey, job_factory: JobFactory) -> bool:
        if key in self._active:
            return False

        self._active.add(key)
        coro = self._run_once(key, job_factory)
        try:
            self._scheduler.create_task(coro)
        except Exception:
            coro.close()
            self._active.discard(key)
            raise
        return True

    async def _run_once(self, key: JobKey, job_factory: JobFactory) -> None:
        try:
            await job_factory()
        except Exception:
            _L.exception(f"upload task failed: {key!r}")
            raise
        finally:
            self._active.discard(key)
