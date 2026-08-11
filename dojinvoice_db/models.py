"""Plain data structures shared by the client, database, crawler and CLI.

The canonical work model is :class:`dlsite_async.Work`; this module only adds
what DLsite exposes but ``dlsite-async`` does not model (sales/price/rating
figures), plus the search-listing query and the crawl option/result records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_PER_PAGE = 100
"""Works per search listing page. 100 is the maximum DLsite accepts."""

DEFAULT_INFO_BATCH = 100
"""Product IDs per ``product/info/ajax`` request."""

_SIZE_UNITS = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
_SIZE_RE = re.compile(r"([\d.,]+)\s*([KMGT]?B)", flags=re.IGNORECASE)


def parse_file_size(value: str | None) -> int | None:
    """Convert a DLsite file size label (``"総計 1.2GB"``) into bytes.

    Returns:
        Size in bytes, or ``None`` when ``value`` holds no recognizable size.
    """
    if not value:
        return None
    m = _SIZE_RE.search(value)
    if not m:
        return None
    try:
        number = float(m.group(1).replace(",", ""))
    except ValueError:  # pragma: no cover - regex already restricts the shape
        return None
    return int(number * _SIZE_UNITS[m.group(2).upper()])


@dataclass(frozen=True)
class SearchQuery:
    """A DLsite search listing (``fsr``) query.

    The defaults reproduce "同人 / 男性向け / ボイス・ASMR, newest first", which is
    the set of works this database is about.
    """

    site: str = "maniax"
    language: str = "jp"
    sex_category: tuple[str, ...] = ("male",)
    work_category: tuple[str, ...] = ("doujin",)
    work_type: tuple[str, ...] = ("SOU",)
    order: str = "release_d"
    per_page: int = DEFAULT_PER_PAGE

    def page_url(self, page: int) -> str:
        """Return the listing URL for the 1-based ``page``."""
        params: list[tuple[str, str]] = [("language", self.language)]
        for key, values in (
            ("sex_category", self.sex_category),
            ("work_category", self.work_category),
            ("work_type", self.work_type),
        ):
            params.extend((f"{key}[{i}]", value) for i, value in enumerate(values))
        params.append(("order[0]", self.order))
        params.append(("per_page", str(self.per_page)))
        params.append(("page", str(page)))
        path = "/".join(f"{quote(k, safe='')}/{quote(v, safe='')}" for k, v in params)
        return f"https://www.dlsite.com/{self.site}/fsr/=/{path}"

    def describe(self) -> str:
        """Return a compact human-readable form, used for logs and crawl state."""
        return (
            f"{self.site}:{'+'.join(self.sex_category)}/{'+'.join(self.work_category)}"
            f"/{'+'.join(self.work_type)}/{self.order}"
        )


def _as_int(value: Any) -> int | None:  # noqa: ANN401 - raw JSON value
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:  # noqa: ANN401 - raw JSON value
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:  # noqa: ANN401 - raw JSON value
    if value is None:
        return None
    return bool(value)


@dataclass(frozen=True)
class WorkStats:
    """Volatile figures for a work (price, sales, ratings).

    These change over time for works already in the database, so they are
    stored separately from the (mostly immutable) work metadata and can be
    refreshed on their own with one request per 100 works.
    """

    product_id: str
    price: int | None = None
    price_without_tax: int | None = None
    official_price: int | None = None
    discount_rate: int | None = None
    dl_count: int | None = None
    wishlist_count: int | None = None
    rate_average: float | None = None
    rate_count: int | None = None
    review_count: int | None = None
    is_sale: bool | None = None
    is_discount: bool | None = None

    @classmethod
    def from_info(cls, product_id: str, info: Mapping[str, Any]) -> WorkStats:
        """Build stats from one ``product/info/ajax`` entry."""
        return cls(
            product_id=product_id,
            price=_as_int(info.get("price")),
            price_without_tax=_as_int(info.get("price_without_tax")),
            official_price=_as_int(info.get("official_price")),
            discount_rate=_as_int(info.get("discount_rate")),
            dl_count=_as_int(info.get("dl_count")),
            wishlist_count=_as_int(info.get("wishlist_count")),
            rate_average=_as_float(info.get("rate_average_2dp")),
            rate_count=_as_int(info.get("rate_count")),
            review_count=_as_int(info.get("review_count")),
            is_sale=_as_bool(info.get("is_sale")),
            is_discount=_as_bool(info.get("is_discount")),
        )


@dataclass
class CrawlOptions:
    """Options for :func:`dojinvoice_db.crawler.crawl`."""

    query: SearchQuery = field(default_factory=SearchQuery)
    max_pages: int | None = None
    stop_after_known_pages: int = 2
    full: bool = False
    limit: int | None = None
    concurrency: int = 4
    interval: float = 0.5
    skip_details: bool = False
    detail_stale_days: int | None = None
    retry_errors: bool = False
    info_batch: int = DEFAULT_INFO_BATCH


@dataclass
class CrawlResult:
    """Counters describing what a crawl did."""

    pages_fetched: int = 0
    ids_seen: int = 0
    new_ids: int = 0
    summaries_written: int = 0
    details_fetched: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return the counters as a plain dict."""
        return {
            "pages_fetched": self.pages_fetched,
            "ids_seen": self.ids_seen,
            "new_ids": self.new_ids,
            "summaries_written": self.summaries_written,
            "details_fetched": self.details_fetched,
            "errors": self.errors,
        }
