"""Request-efficient access layer over :mod:`dlsite_async`.

Three kinds of request are used, in increasing cost per work:

1. **Search listing** (:meth:`DlsiteClient.fetch_listing_ids`) — one request
   returns up to 100 product IDs, newest first.
2. **Product info ajax** (:meth:`DlsiteClient.fetch_product_info`) — DLsite's
   ``product/info/ajax`` endpoint accepts a comma-separated list of product
   IDs, so one request covers up to 100 works. It yields everything
   ``DlsiteAPI.product_info()`` yields (title, maker, work type, release date,
   cover image) *plus* the price/sales/rating figures.
3. **Work page HTML** (:meth:`DlsiteClient.fetch_detail`) — one request per
   work, the only source for circle name, description, genres and the
   voice actor / scenario / illustration / music credits.

Only step 3 scales with the number of works, so the crawler performs it once
per work and never again unless explicitly asked to.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Self

from aiohttp import ClientError, ClientResponseError, ClientTimeout
from dlsite_async import AgeCategory, BookType, DlsiteAPI, Work, WorkType

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from types import TracebackType

    from .models import SearchQuery

LOGGER = logging.getLogger(__name__)

USER_AGENT = "dojinvoice-db (+https://github.com/eggplants/dojinvoice_db)"

INFO_URL = "https://www.dlsite.com/maniax/product/info/ajax"

_PRODUCT_ID_RE = re.compile(r'data-list_item_product_id="([A-Z]{2}\d+)"')

_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _import_parse_work_html() -> Callable[[str], dict[str, Any]] | None:
    """Return ``dlsite-async``'s work page parser, or ``None`` if it moved.

    It lives in a private module, so the import is guarded: if a future
    release restructures it, :meth:`DlsiteClient.fetch_detail` falls back to
    the public (but twice as expensive) ``DlsiteAPI.get_work``.
    """
    try:
        module = importlib.import_module("dlsite_async._scraper")
    except ImportError:  # pragma: no cover - only if dlsite-async restructures
        return None
    return getattr(module, "parse_work_html", None)


parse_work_html = _import_parse_work_html()


class WorkNotFoundError(Exception):
    """A work page could not be retrieved (removed, private or wrong ID)."""


def extract_product_ids(html: str) -> list[str]:
    """Return the product IDs listed on a search results page, in page order.

    Duplicates are dropped while preserving the first occurrence.
    """
    return list(dict.fromkeys(match.group(1) for match in _PRODUCT_ID_RE.finditer(html)))


def _to_datetime(value: Any) -> datetime | None:  # noqa: ANN401 - raw JSON value
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)  # noqa: DTZ007 - DLsite times are naive JST
        except ValueError:
            continue
    return None


def work_from_info(product_id: str, info: Mapping[str, Any]) -> Work:
    """Build a :class:`~dlsite_async.Work` from one ajax info entry.

    Unlike ``DlsiteAPI.product_info()`` this never raises on unfamiliar enum
    values -- DLsite occasionally introduces new work/book types, and dropping
    the field is better than dropping the work.
    """
    data = dict(info)
    data["product_id"] = product_id
    data["age_category"] = _enum_or_none(AgeCategory, data.get("age_category"))
    data["work_type"] = _enum_or_none(WorkType, data.get("work_type"))
    book_type = data.get("book_type")
    if isinstance(book_type, dict):
        book_type = book_type.get("value")
    data["book_type"] = _enum_or_none(BookType, book_type)
    data["regist_date"] = _to_datetime(data.get("regist_date"))
    return Work.from_dict(data)


def _enum_or_none(enum_cls: Any, value: Any) -> Any:  # noqa: ANN401 - generic enum helper
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        LOGGER.debug("unknown %s value: %r", enum_cls.__name__, value)
        return None


class _Throttle:
    """Serialize requests so that at least ``interval`` seconds pass between them."""

    def __init__(self, interval: float) -> None:
        self._interval = max(interval, 0.0)
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        """Block until the next request is allowed to start."""
        if not self._interval:
            return
        async with self._lock:
            now = time.monotonic()
            delay = self._next - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.monotonic()
            self._next = now + self._interval


class DlsiteClient:
    """An HTTP session against DLsite with throttling, retries and counters.

    Args:
        locale: Optional DLsite locale (e.g. ``en_US``). Defaults to Japanese.
        interval: Minimum seconds between requests.
        concurrency: Maximum number of in-flight requests.
        retries: Attempts per request on transient failures.
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        *,
        locale: str | None = None,
        interval: float = 0.5,
        concurrency: int = 4,
        retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self.api = DlsiteAPI(locale=locale)
        self._throttle = _Throttle(interval)
        self._semaphore = asyncio.Semaphore(max(concurrency, 1))
        self._retries = max(retries, 1)
        self._timeout = ClientTimeout(total=timeout)
        self.request_count = 0

    async def __aenter__(self) -> Self:
        """Enter the client session."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the client session."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self.api.close()

    async def _get_text(self, url: str, *, params: Mapping[str, str] | None = None) -> str | None:
        """GET ``url`` and return its body, or ``None`` on a 404/403.

        Retries transient failures with exponential backoff.
        """
        last_error: Exception | None = None
        for attempt in range(self._retries):
            async with self._semaphore:
                await self._throttle.wait()
                self.request_count += 1
                try:
                    async with self.api.get(
                        url,
                        params=dict(params or {}),
                        headers={"User-Agent": USER_AGENT},
                        timeout=self._timeout,
                    ) as response:
                        return await response.text()
                except ClientResponseError as e:
                    if e.status not in _RETRY_STATUSES:
                        if e.status in {403, 404}:
                            return None
                        raise
                    last_error = e
                except (ClientError, TimeoutError) as e:
                    last_error = e
            backoff = 2.0**attempt
            LOGGER.warning("request failed (%s), retrying in %.0fs: %s", last_error, backoff, url)
            await asyncio.sleep(backoff)
        msg = f"giving up on {url}: {last_error}"
        raise WorkNotFoundError(msg) from last_error

    async def fetch_listing_ids(self, query: SearchQuery, page: int) -> list[str]:
        """Return the product IDs on ``page`` of the ``query`` listing."""
        html = await self._get_text(query.page_url(page))
        if html is None:
            return []
        return extract_product_ids(html)

    async def fetch_product_info(self, product_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Return raw ajax info for up to ~100 product IDs in a single request.

        IDs DLsite does not know about are simply absent from the result.
        """
        if not product_ids:
            return {}
        text = await self._get_text(INFO_URL, params={"product_id": ",".join(product_ids)})
        if not text:
            return {}
        try:
            data = json.loads(text)
        except ValueError:
            LOGGER.warning("malformed info response for %d ids", len(product_ids))
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(v, dict)}

    async def fetch_detail(self, work: Work) -> Work:
        """Fill in the work-page-only fields of ``work``.

        Raises:
            WorkNotFoundError: Neither the work nor the announce page exists.
        """
        if parse_work_html is None:  # pragma: no cover - dependency fallback
            return await self.api.get_work(work.product_id)
        site_id = work.site_id or "maniax"
        for kind in ("work", "announce"):
            url = f"https://www.dlsite.com/{site_id}/{kind}/=/product_id/{work.product_id}.html/"
            html = await self._get_text(url)
            if html:
                return replace(work, **parse_work_html(html))
        msg = f"no work or announce page for {work.product_id}"
        raise WorkNotFoundError(msg)


def batched(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    """Split ``items`` into consecutive chunks of at most ``size``."""
    step = max(size, 1)
    for start in range(0, len(items), step):
        yield items[start : start + step]
