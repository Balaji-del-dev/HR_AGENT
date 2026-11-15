"""Run ORM work on the graph's main thread while an inner agent loop runs on a helper thread.

LangChain's create_agent executes tools in a thread pool. Django connections and
the tenant scope are per thread, so tool calls are handed back to the thread
that owns them. The model calls stay on the helper thread.
"""

import contextvars
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, TypeVar

T = TypeVar("T")


class MainThreadBridge:
    def __init__(self) -> None:
        self._owner = threading.get_ident()
        self._queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any], Future[Any]]] = (
            queue.Queue()
        )

    def submit(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        if threading.get_ident() == self._owner:
            return fn(*args, **kwargs)
        future: Future[T] = Future()
        self._queue.put((fn, args, kwargs, future))
        return future.result()

    def run(self, target: Callable[[], T]) -> T:
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["value"] = target()
            except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread below
                outcome["error"] = exc

        context = contextvars.copy_context()
        worker = threading.Thread(target=context.run, args=(work,), daemon=True, name="agent-loop")
        worker.start()
        while worker.is_alive() or not self._queue.empty():
            try:
                fn, args, kwargs, future = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                future.set_result(fn(*args, **kwargs))
            except BaseException as exc:  # noqa: BLE001 - delivered to the waiting tool call
                future.set_exception(exc)
        worker.join()
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]  # type: ignore[no-any-return]
