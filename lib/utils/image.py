from functools import cache
from pathlib import PurePosixPath, Path
from urllib.parse import urlparse, urlunparse

from typing import Callable, Awaitable, Literal
import re
from PIL import Image
from io import BytesIO

import anyio
import aiolimiter

import filetype
import httpx
import resvg_py
from pydantic_ai import BinaryImage

from lib.utils.datasets import get_task_root


HTTPGet = Callable[[str], Awaitable[httpx.Response]]


def create_rate_limited_async_httpx_get(
    max_rate: int = 5,
    time_period: float = 60.0,
    concurrency: int = 1,
    timeout: int = 30,
    connect: int = 5,
    max_redirects: int = 10,
    user_agent: str | None = None,
) -> HTTPGet:
    httpx_async_client: httpx.AsyncClient = create_httpx_async_client(
        timeout=timeout,
        connect=connect,
        max_redirects=max_redirects,
        user_agent=user_agent,
    )
    limiter = aiolimiter.AsyncLimiter(max_rate=max_rate, time_period=time_period)
    semaphore = anyio.Semaphore(concurrency)

    async def httpx_get(image_url: str) -> httpx.Response:
        async with limiter:
            async with semaphore:
                return await httpx_async_client.get(image_url)

    return httpx_get


def create_httpx_async_client(
    timeout: int = 30,
    connect: int = 5,
    max_redirects: int = 10,
    user_agent: str | None = None,
) -> httpx.AsyncClient:
    client = _create_httpx_async_client(
        timeout=timeout,
        connect=connect,
        max_redirects=max_redirects,
        user_agent=user_agent,
    )
    if client.is_closed:
        _create_httpx_async_client.cache_clear()
        client = _create_httpx_async_client(
            timeout=timeout,
            connect=connect,
            max_redirects=max_redirects,
            user_agent=user_agent,
        )
    return client


@cache
def _create_httpx_async_client(
    timeout: int = 30,
    connect: int = 5,
    max_redirects: int = 10,
    user_agent: str | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout=timeout, connect=connect),
        headers={"User-Agent": user_agent} if user_agent else None,
        max_redirects=max_redirects,
    )


async def load_image_from_url(image_url: str, httpx_get: HTTPGet) -> BinaryImage:
    """Loads an image from the given URL."""
    try:
        if image_url.endswith(".svg"):
            if thumbnail_url := get_thumbnail_from_url(
                image_url=image_url,
                language="langzh-hans",
            ):
                image_url = thumbnail_url
        with anyio.fail_after(30):
            return await raw_load_image_from_url(
                image_url=image_url, httpx_get=httpx_get
            )
    except (httpx.TimeoutException, TimeoutError):
        if thumbnail_url := get_thumbnail_from_url(
            image_url=image_url,
        ):
            image_url = thumbnail_url
            return await raw_load_image_from_url(
                image_url=image_url, httpx_get=httpx_get
            )
        else:
            raise ValueError("Cannot load image within timeout")


async def raw_load_image_from_url(image_url: str, httpx_get: HTTPGet) -> BinaryImage:
    response = await httpx_get(image_url)

    image_content = response.content
    response.raise_for_status()
    if content_type := response.headers.get("content-type"):
        content_type = content_type.split(";")[0]
        if content_type == "application/octet-stream":
            content_type = filetype.guess_mime(image_content)
            if content_type is None:
                raise ValueError(f"Cannot get mimetype from url={image_url}")

    if content_type.startswith("image/svg"):
        return svg_to_png(svg_string=response.text)

    if not any(
        content_type.startswith(mime)
        for mime in [
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/heic",
            "image/heif",
        ]
    ):
        print(f"convert {content_type} to image/png")
        return not_supported_image_to_png(image_content=image_content)

    return BinaryImage(data=image_content, media_type=content_type)


def svg_to_png(svg_string: str) -> BinaryImage:
    image_content = resvg_py.svg_to_bytes(
        svg_string=svg_string,
        width=1920,
        languages=["zh-Hans", "zh-CN", "zh", "en"],
    )

    return BinaryImage(data=image_content, media_type="image/png")


def not_supported_image_to_png(image_content: bytes) -> BinaryImage:
    image = Image.open(BytesIO(image_content))

    image = image.convert("RGBA")
    png_bytes = BytesIO()
    image.save(png_bytes, format="PNG")
    return BinaryImage(data=png_bytes.getvalue(), media_type="image/png")


def get_thumbnail_from_url(
    image_url: str,
    language: str | None = None,
    resolution: Literal[
        "20", "40", "60", "120", "250", "330", "500", "960", "1280", "1920", "3840"
    ] = "1920",
) -> str | None:
    if "upload.wikimedia.org" in image_url:
        if "thumb/" in image_url:
            return image_url
        parsed = urlparse(image_url)
        path = PurePosixPath(parsed.path)
        parts = path.parts
        try:
            idx = parts.index("commons")
        except ValueError:
            raise ValueError("Not a valid Wikimedia Commons URL")
        sub_path = PurePosixPath(*parts[idx + 1 :])
        thumb_path = PurePosixPath(
            *parts[: idx + 1],  # /wikipedia/commons
            "thumb",
            sub_path,
            f"{language + '-' if language else ''}{resolution}px-{sub_path.name}.png",
        )

        thumb_image_url = urlunparse(
            parsed._replace(path=str(thumb_path), query="", fragment="")
        )

        return thumb_image_url

    return None


def load_images_from_disk(path: Path, case_id: str) -> list[BinaryImage]:
    if not path.is_dir():
        raise NotADirectoryError(f"{path!r} is not a directory")

    pattern: re.Pattern[str] = re.compile(
        r"^" + re.escape(case_id) + r"_([1-9][0-9]*)\.png$"
    )

    matched: list[tuple[int, Path]] = []
    for file in path.iterdir():
        if not file.is_file():
            continue
        m = pattern.match(file.name)
        if m:
            n = int(m.group(1))
            matched.append((n, file))

    matched.sort(key=lambda t: t[0])

    return [
        BinaryImage(data=file.read_bytes(), media_type="image/png")
        for _, file in matched
    ]


def load_images_from_task(task_name: str, case_id: str):
    return load_images_from_disk(
        path=get_task_root(task_name) / "images", case_id=case_id
    )
