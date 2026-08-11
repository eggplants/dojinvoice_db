"""Crawl orchestration: discover works, then fill them in as cheaply as possible.

A run has three stages, each of which can be skipped or resumed independently:

1. **Discover** — walk the search listing newest-first. Because the listing is
   ordered by release date, an incremental run only needs to read until it has
   seen ``stop_after_known_pages`` consecutive pages containing nothing new;
   everything older is already stored. ``--full`` disables that early stop.
2. **Summarize** — one batched ajax request per 100 new IDs writes the work
   row and its price/sales/rating figures.
3. **Detail** — one request per work whose ``detail_fetched_at`` is NULL (or
   stale). Interrupting a run leaves the remaining works marked pending, so
   the next run picks up exactly where this one stopped instead of refetching.

The stage functions all take a :class:`CrawlSession`, which carries the
database, the client, the options and the counters they update.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .dlsite import WorkNotFoundError, batched, work_from_info
from .models import CrawlOptions, CrawlResult, WorkStats

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .db import WorkDatabase
    from .dlsite import DlsiteClient

LOGGER = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def _now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class CrawlSession:
    """Everything a crawl stage needs: where to read from, write to and report."""

    db: WorkDatabase
    client: DlsiteClient
    options: CrawlOptions = field(default_factory=CrawlOptions)
    result: CrawlResult = field(default_factory=CrawlResult)
    progress: ProgressFn = _noop


async def discover_ids(session: CrawlSession) -> list[str]:
    """Walk the search listing and return product IDs not yet in the database."""
    options = session.options
    known = session.db.known_product_ids()
    new_ids: list[str] = []
    picked: set[str] = set()
    consecutive_known = 0
    page = 1
    while options.max_pages is None or page <= options.max_pages:
        ids = await session.client.fetch_listing_ids(options.query, page)
        session.result.pages_fetched += 1
        if not ids:
            session.progress(f"page {page}: empty, listing exhausted")
            break
        session.result.ids_seen += len(ids)
        fresh = [pid for pid in ids if pid not in known and pid not in picked]
        picked.update(fresh)
        new_ids.extend(fresh)
        session.progress(f"page {page}: {len(ids)} works, {len(fresh)} new (total new: {len(new_ids)})")
        consecutive_known = 0 if fresh else consecutive_known + 1
        if not options.full and consecutive_known >= options.stop_after_known_pages:
            session.progress(f"stopping: {consecutive_known} consecutive pages with nothing new")
            break
        if options.limit is not None and len(new_ids) >= options.limit:
            break
        page += 1
    if options.limit is not None:
        del new_ids[options.limit :]
    return new_ids


async def store_summaries(session: CrawlSession, product_ids: Sequence[str]) -> None:
    """Fetch and store ajax info for ``product_ids``, 100 works per request."""
    done = 0
    for chunk in batched(product_ids, session.options.info_batch):
        info = await session.client.fetch_product_info(chunk)
        now = _now()
        for product_id in chunk:
            entry = info.get(product_id)
            if entry is None:
                session.db.record_error(product_id, "not returned by product info ajax", now=now)
                session.result.errors += 1
                continue
            session.db.upsert_work(work_from_info(product_id, entry), detail=False, now=now)
            session.db.upsert_stats(WorkStats.from_info(product_id, entry), now=now)
            session.result.summaries_written += 1
        done += len(chunk)
        session.progress(f"summaries: {done}/{len(product_ids)}")


async def fetch_details(session: CrawlSession, product_ids: Sequence[str]) -> None:
    """Fetch the work page of each ID and store the detail-only fields.

    Runs ``options.concurrency`` fetches at a time; database writes happen on
    the event loop thread, so each work is committed as soon as it arrives and
    an interrupted run keeps everything fetched so far.
    """
    if not product_ids:
        return
    queue: asyncio.Queue[str] = asyncio.Queue()
    for product_id in product_ids:
        queue.put_nowait(product_id)
    total = len(product_ids)
    handled = 0

    async def worker() -> None:
        nonlocal handled
        while True:
            try:
                product_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            work = session.db.load_work(product_id)
            if work is None:  # pragma: no cover - only if the row vanished mid-run
                continue
            try:
                detailed = await session.client.fetch_detail(work)
            except WorkNotFoundError as e:
                session.db.record_error(product_id, str(e))
                session.result.errors += 1
            except Exception as e:  # noqa: BLE001 - one bad work must not abort the run
                LOGGER.warning("failed to fetch %s: %s", product_id, e)
                session.db.record_error(product_id, f"{type(e).__name__}: {e}")
                session.result.errors += 1
            else:
                session.db.upsert_work(detailed, detail=True, now=_now())
                session.db.clear_error(product_id)
                session.result.details_fetched += 1
            handled += 1
            session.progress(f"details: {handled}/{total} ({product_id})")

    await asyncio.gather(*(worker() for _ in range(max(session.options.concurrency, 1))))


def pending_detail_ids(session: CrawlSession) -> list[str]:
    """Return the works whose detail page this session should fetch."""
    options = session.options
    stale_before = None
    if options.detail_stale_days is not None:
        stale_before = _now() - timedelta(days=options.detail_stale_days)
    return session.db.pending_detail_ids(
        limit=options.limit,
        stale_before=stale_before,
        retry_errors=options.retry_errors,
    )


async def crawl(session: CrawlSession) -> CrawlResult:
    """Run a full discover -> summarize -> detail pass."""
    new_ids = await discover_ids(session)
    session.result.new_ids = len(new_ids)
    if new_ids:
        await store_summaries(session, new_ids)
    if not session.options.skip_details:
        pending = pending_detail_ids(session)
        session.progress(f"details pending: {len(pending)}")
        await fetch_details(session, pending)
    session.db.set_state("last_crawl_at", _now().isoformat(sep=" ", timespec="seconds"))
    session.db.set_state("last_query", session.options.query.describe())
    return session.result


async def refresh_stats(session: CrawlSession, product_ids: Sequence[str]) -> tuple[int, int]:
    """Re-fetch price/sales/rating figures for ``product_ids``.

    The batched ajax endpoint also returns the cheap metadata columns, so the
    work rows are refreshed at no extra cost -- useful for announced works
    whose title or release date changes before release.

    Returns:
        ``(updated, missing)`` counts.
    """
    updated = 0
    missing = 0
    for chunk in batched(product_ids, session.options.info_batch):
        info = await session.client.fetch_product_info(chunk)
        now = _now()
        for product_id in chunk:
            entry = info.get(product_id)
            if entry is None:
                missing += 1
                continue
            session.db.upsert_work(work_from_info(product_id, entry), detail=False, now=now)
            session.db.upsert_stats(WorkStats.from_info(product_id, entry), now=now)
            updated += 1
        session.progress(f"stats: {updated + missing}/{len(product_ids)}")
    return updated, missing
