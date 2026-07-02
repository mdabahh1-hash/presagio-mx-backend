"""Fire-and-forget background tasks that won't be garbage-collected mid-flight.

asyncio only keeps weak references to tasks, so a bare `asyncio.create_task(...)`
whose result is discarded can be GC'd before it finishes (a documented CPython
gotcha). `spawn()` holds a strong reference until the task completes.
"""
import asyncio

_tasks: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task
