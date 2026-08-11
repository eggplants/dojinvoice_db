"""Command-line interface for building the DLsite voice work database.

Subcommands::

    dvdb crawl    # discover new works and fill them in (the usual cron job)
    dvdb details  # fetch only the work pages still missing, no listing reads
    dvdb refresh  # re-fetch price/sales/rating figures, 100 works per request
    dvdb show ID  # print one stored work
    dvdb stats    # summarize the database

``crawl`` is incremental by design: the listing is read newest-first and stops
after ``--stop-after-known-pages`` consecutive pages that contain nothing new,
and each work's detail page is fetched at most once. Re-running it therefore
costs a handful of requests plus one per newly released work.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from . import __version__, crawler
from .db import SchemaVersionError, WorkDatabase
from .dlsite import DlsiteClient
from .models import DEFAULT_INFO_BATCH, DEFAULT_PER_PAGE, CrawlOptions, SearchQuery

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_DB = "dojinvoice.db"
DEFAULT_REFRESH_STALE_DAYS = 7


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return int(args.func(args))
    except SchemaVersionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\naborted (fetched data is already committed)", file=sys.stderr)
        return 130
    except BrokenPipeError:  # pragma: no cover - stdout closed by a pager
        return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="dvdb",
        description="Build and incrementally update a SQLite DB of DLsite doujin voice works.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_crawl = sub.add_parser("crawl", help="Discover new works and fetch their metadata.")
    _add_common_args(p_crawl)
    _add_network_args(p_crawl)
    _add_query_args(p_crawl)
    p_crawl.add_argument("--max-pages", type=int, help="stop after reading this many listing pages.")
    p_crawl.add_argument(
        "--stop-after-known-pages",
        type=int,
        default=2,
        metavar="N",
        help="stop once N consecutive listing pages contain no new work (default: 2).",
    )
    p_crawl.add_argument(
        "--full",
        action="store_true",
        help="read the whole listing instead of stopping early (for the initial build).",
    )
    p_crawl.add_argument("--limit", type=int, help="process at most this many works.")
    p_crawl.add_argument(
        "--skip-details",
        action="store_true",
        help="only record listing/ajax metadata; leave work pages for a later run.",
    )
    p_crawl.add_argument(
        "--detail-stale-days",
        type=int,
        metavar="DAYS",
        help="also re-fetch work pages older than DAYS (default: never).",
    )
    p_crawl.add_argument("--retry-errors", action="store_true", help="retry works that previously failed.")
    p_crawl.set_defaults(func=cmd_crawl)

    p_details = sub.add_parser("details", help="Fetch work pages still missing from the database.")
    _add_common_args(p_details)
    _add_network_args(p_details)
    p_details.add_argument("--limit", type=int, help="fetch at most this many work pages.")
    p_details.add_argument(
        "--stale-days",
        type=int,
        metavar="DAYS",
        help="also re-fetch work pages older than DAYS.",
    )
    p_details.add_argument("--retry-errors", action="store_true", help="retry works that previously failed.")
    p_details.set_defaults(func=cmd_details)

    p_refresh = sub.add_parser("refresh", help="Re-fetch price/sales/rating figures for stored works.")
    _add_common_args(p_refresh)
    _add_network_args(p_refresh)
    p_refresh.add_argument("--limit", type=int, help="refresh at most this many works.")
    p_refresh.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_REFRESH_STALE_DAYS,
        metavar="DAYS",
        help=f"only refresh works whose figures are older than DAYS (default: {DEFAULT_REFRESH_STALE_DAYS}).",
    )
    p_refresh.add_argument("--all", action="store_true", help="refresh every work regardless of age.")
    p_refresh.add_argument(
        "--batch",
        type=int,
        default=DEFAULT_INFO_BATCH,
        help=f"product IDs per request (default: {DEFAULT_INFO_BATCH}).",
    )
    p_refresh.set_defaults(func=cmd_refresh)

    p_show = sub.add_parser("show", help="Print one stored work.")
    _add_common_args(p_show)
    p_show.add_argument("product_id", metavar="WORK_ID", help="DLsite product ID, e.g. RJ01234567.")
    p_show.add_argument("--json", action="store_true", help="print as JSON instead of a text summary.")
    p_show.set_defaults(func=cmd_show)

    p_stats = sub.add_parser("stats", help="Summarize the database.")
    _add_common_args(p_stats)
    p_stats.add_argument("--json", action="store_true", help="print as JSON instead of a text summary.")
    p_stats.add_argument("--top", type=int, default=10, help="rows per ranking (default: 10).")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=DEFAULT_DB, metavar="PATH", help=f"database path (default: {DEFAULT_DB}).")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging.")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress output.")


def _add_network_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="minimum delay between requests (default: 0.5).",
    )
    parser.add_argument(
        "-j",
        "--concurrency",
        type=int,
        default=4,
        help="maximum simultaneous requests (default: 4).",
    )
    parser.add_argument("--retries", type=int, default=3, help="attempts per request (default: 3).")
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request timeout in seconds (default: 30).")
    parser.add_argument("--locale", help="DLsite locale, e.g. en_US (default: Japanese).")


def _add_query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--site", default="maniax", help="DLsite site segment (default: maniax).")
    parser.add_argument(
        "--sex-category",
        action="append",
        metavar="VALUE",
        help="male / female; may repeat (default: male).",
    )
    parser.add_argument(
        "--work-category",
        action="append",
        metavar="VALUE",
        help="doujin / pc / app; may repeat (default: doujin).",
    )
    parser.add_argument(
        "--work-type",
        action="append",
        metavar="CODE",
        help="DLsite work type code; may repeat (default: SOU, voice/ASMR).",
    )
    parser.add_argument("--order", default="release_d", help="listing order (default: release_d, newest first).")
    parser.add_argument(
        "--per-page",
        type=int,
        default=DEFAULT_PER_PAGE,
        help=f"works per listing page (default: {DEFAULT_PER_PAGE}).",
    )


def _query_from_args(args: argparse.Namespace) -> SearchQuery:
    return SearchQuery(
        site=args.site,
        sex_category=tuple(args.sex_category or ("male",)),
        work_category=tuple(args.work_category or ("doujin",)),
        work_type=tuple(args.work_type or ("SOU",)),
        order=args.order,
        per_page=args.per_page,
    )


def _make_progress(args: argparse.Namespace) -> Callable[[str], None]:
    if args.quiet:
        return lambda _: None
    stream = sys.stderr
    interactive = stream.isatty()

    def progress(message: str) -> None:
        if interactive:
            print(f"\r\033[2K{message}", end="", file=stream, flush=True)
        else:
            print(message, file=stream, flush=True)

    return progress


def _finish_progress(args: argparse.Namespace) -> None:
    if not args.quiet and sys.stderr.isatty():
        print(file=sys.stderr)


def _client(args: argparse.Namespace) -> DlsiteClient:
    return DlsiteClient(
        locale=args.locale,
        interval=args.interval,
        concurrency=args.concurrency,
        retries=args.retries,
        timeout=args.timeout,
    )


def cmd_crawl(args: argparse.Namespace) -> int:
    """`dvdb crawl`: discover new works and fetch their metadata."""
    options = CrawlOptions(
        query=_query_from_args(args),
        max_pages=args.max_pages,
        stop_after_known_pages=args.stop_after_known_pages,
        full=args.full,
        limit=args.limit,
        concurrency=args.concurrency,
        interval=args.interval,
        skip_details=args.skip_details,
        detail_stale_days=args.detail_stale_days,
        retry_errors=args.retry_errors,
    )
    progress = _make_progress(args)

    async def run() -> tuple[dict[str, int], int]:
        with WorkDatabase(args.db) as db:
            async with _client(args) as client:
                session = crawler.CrawlSession(db=db, client=client, options=options, progress=progress)
                result = await crawler.crawl(session)
                return result.as_dict(), client.request_count

    counters, requests = asyncio.run(run())
    _finish_progress(args)
    if not args.quiet:
        print(
            "crawl done: "
            f"{counters['new_ids']} new, {counters['summaries_written']} summaries, "
            f"{counters['details_fetched']} details, {counters['errors']} errors "
            f"({counters['pages_fetched']} listing pages, {requests} requests)",
        )
    return 0


def cmd_details(args: argparse.Namespace) -> int:
    """`dvdb details`: fetch work pages for works that still lack them."""
    options = CrawlOptions(
        limit=args.limit,
        concurrency=args.concurrency,
        interval=args.interval,
        detail_stale_days=args.stale_days,
        retry_errors=args.retry_errors,
    )
    progress = _make_progress(args)

    async def run() -> tuple[int, int, int]:
        with WorkDatabase(args.db) as db:
            async with _client(args) as client:
                session = crawler.CrawlSession(db=db, client=client, options=options, progress=progress)
                pending = crawler.pending_detail_ids(session)
                progress(f"details pending: {len(pending)}")
                await crawler.fetch_details(session, pending)
                return session.result.details_fetched, session.result.errors, client.request_count

    fetched, errors, requests = asyncio.run(run())
    _finish_progress(args)
    if not args.quiet:
        print(f"details done: {fetched} fetched, {errors} errors ({requests} requests)")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    """`dvdb refresh`: re-fetch price/sales/rating figures."""
    progress = _make_progress(args)
    stale_before = None if args.all else datetime.now().astimezone() - timedelta(days=args.stale_days)

    async def run() -> tuple[int, int, int]:
        with WorkDatabase(args.db) as db:
            product_ids = db.stale_stat_ids(stale_before=stale_before, limit=args.limit)
            progress(f"stats to refresh: {len(product_ids)}")
            async with _client(args) as client:
                session = crawler.CrawlSession(
                    db=db,
                    client=client,
                    options=CrawlOptions(info_batch=args.batch),
                    progress=progress,
                )
                updated, missing = await crawler.refresh_stats(session, product_ids)
                return updated, missing, client.request_count

    updated, missing, requests = asyncio.run(run())
    _finish_progress(args)
    if not args.quiet:
        print(f"refresh done: {updated} updated, {missing} unavailable ({requests} requests)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """`dvdb show`: print one stored work."""
    with WorkDatabase(args.db) as db:
        work = db.get_work(args.product_id.upper())
    if work is None:
        print(f"error: {args.product_id} is not in {args.db}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(work, ensure_ascii=False, indent=2))
        return 0
    _print_work(work)
    return 0


def _print_work(work: dict[str, Any]) -> None:
    stats = work.get("stats") or {}
    rows: list[tuple[str, Any]] = [
        ("product id", work["product_id"]),
        ("title", work["work_name"]),
        ("circle", f"{work['circle']} ({work['maker_id']})" if work["circle"] else work["maker_id"]),
        ("series", work["series"]),
        ("release", work["regist_date"]),
        ("age", work["age_category"]),
        ("work type", work["work_type"]),
        ("file", f"{work['file_size']}" if work["file_size"] else None),
        ("formats", ", ".join(work["file_formats"]) or None),
        ("price", stats.get("price")),
        ("sales", stats.get("dl_count")),
        ("rating", f"{stats['rate_average']} ({stats.get('rate_count')})" if stats.get("rate_average") else None),
        ("wishlist", stats.get("wishlist_count")),
        ("url", work["work_url"]),
    ]
    for role, names in (work.get("creators") or {}).items():
        rows.append((role.replace("_", " "), ", ".join(names)))
    rows.append(("genres", ", ".join(work["genres"]) or None))
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        if value not in (None, ""):
            print(f"{label:<{width}}  {value}")
    if work.get("description"):
        print()
        print(work["description"])


def cmd_stats(args: argparse.Namespace) -> int:
    """`dvdb stats`: summarize the database."""
    with WorkDatabase(args.db) as db:
        summary = db.summary()
        rankings = {
            "circles": db.top_rows(
                "select circle, maker_id, count(*) as works from work"
                " where circle is not null group by maker_id order by works desc limit ?",
                (args.top,),
            ),
            "voice_actors": db.top_rows(
                "select name, count(*) as works from work_creator where role = 'voice_actor'"
                " group by name order by works desc limit ?",
                (args.top,),
            ),
            "genres": db.top_rows(
                "select genre, count(*) as works from work_genre group by genre order by works desc limit ?",
                (args.top,),
            ),
        }
    if args.json:
        print(json.dumps({"summary": summary, "top": rankings}, ensure_ascii=False, indent=2))
        return 0
    for key, value in summary.items():
        print(f"{key:<16}  {value if value is not None else '-'}")
    for title, key, label in (
        ("Top circles", "circles", "circle"),
        ("Top voice actors", "voice_actors", "name"),
        ("Top genres", "genres", "genre"),
    ):
        rows = rankings[key]
        if not rows:
            continue
        print(f"\n{title}")
        for row in rows:
            print(f"  {row['works']:>6}  {row[label]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
