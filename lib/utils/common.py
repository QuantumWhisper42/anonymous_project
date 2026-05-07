import asyncio
import functools
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def sync(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    return wrapper
