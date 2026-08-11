"""SQLite storage for DLsite voice works.

The schema separates three kinds of data by how expensive they are to obtain
and how often they change:

* ``work`` — metadata. ``summary_fetched_at`` marks the cheap ajax-sourced
  columns, ``detail_fetched_at`` the ones that cost one request per work.
  A NULL ``detail_fetched_at`` is the resume marker: those works are picked up
  by the next run.
* ``work_stat`` (+ ``work_stat_history``) — price/sales/rating figures, which
  keep changing and can be refreshed in batches of 100 works per request.
* ``work_creator`` / ``work_genre`` / ``work_file_format`` / ``work_event`` /
  ``work_sample_image`` — the multi-valued detail fields.

``fetch_error`` remembers works that failed so repeated runs do not keep
re-requesting them, and ``crawl_state`` holds bookkeeping between runs.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from dlsite_async import AgeCategory, BookType, Work, WorkType

from .models import parse_file_size

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from .models import WorkStats

SCHEMA_VERSION = 1

MAX_ERROR_ATTEMPTS = 3
"""Works that failed this many times are skipped unless ``--retry-errors``."""

CREATOR_ROLES = ("voice_actor", "scenario", "illustration", "music", "author", "writer")
"""``Work`` list attributes stored as ``work_creator`` rows."""

_SCHEMA = """
create table work (
    product_id         text primary key,
    site_id            text,
    maker_id           text,
    work_name          text not null,
    work_name_masked   text,
    age_category       integer,
    work_type          text,
    book_type          text,
    work_image         text,
    regist_date        text,
    announce_date      text,
    modified_date      text,
    series             text,
    circle             text,
    brand              text,
    publisher          text,
    label              text,
    description        text,
    file_size          text,
    file_size_bytes    integer,
    page_count         integer,
    work_url           text,
    first_seen_at      text not null,
    summary_fetched_at text,
    detail_fetched_at  text
);
create index work_regist_date_idx on work (regist_date desc);
create index work_maker_idx on work (maker_id);
create index work_type_idx on work (work_type);
create index work_detail_pending_idx on work (detail_fetched_at);

create table work_stat (
    product_id        text primary key references work (product_id) on delete cascade,
    price             integer,
    price_without_tax integer,
    official_price    integer,
    discount_rate     integer,
    dl_count          integer,
    wishlist_count    integer,
    rate_average      real,
    rate_count        integer,
    review_count      integer,
    is_sale           integer,
    is_discount       integer,
    fetched_at        text not null
);

create table work_stat_history (
    product_id     text not null references work (product_id) on delete cascade,
    fetched_at     text not null,
    price          integer,
    dl_count       integer,
    wishlist_count integer,
    rate_average   real,
    rate_count     integer,
    review_count   integer
);
create index work_stat_history_idx on work_stat_history (product_id, fetched_at);

create table work_creator (
    product_id text not null references work (product_id) on delete cascade,
    role       text not null,
    name       text not null,
    primary key (product_id, role, name)
);
create index work_creator_name_idx on work_creator (name);

create table work_genre (
    product_id text not null references work (product_id) on delete cascade,
    genre      text not null,
    primary key (product_id, genre)
);
create index work_genre_idx on work_genre (genre);

create table work_file_format (
    product_id  text not null references work (product_id) on delete cascade,
    file_format text not null,
    primary key (product_id, file_format)
);

create table work_event (
    product_id text not null references work (product_id) on delete cascade,
    event      text not null,
    primary key (product_id, event)
);

create table work_sample_image (
    product_id text not null references work (product_id) on delete cascade,
    idx        integer not null,
    url        text not null,
    primary key (product_id, idx)
);

create table fetch_error (
    product_id      text primary key,
    attempts        integer not null default 0,
    last_error      text,
    last_attempt_at text
);

create table crawl_state (
    key   text primary key,
    value text
);

create view work_full as
select
    w.*,
    s.price,
    s.dl_count,
    s.wishlist_count,
    s.rate_average,
    s.rate_count,
    s.review_count,
    (select group_concat(c.name, ', ') from work_creator c
      where c.product_id = w.product_id and c.role = 'voice_actor') as voice_actors,
    (select group_concat(c.name, ', ') from work_creator c
      where c.product_id = w.product_id and c.role = 'scenario') as scenarios,
    (select group_concat(c.name, ', ') from work_creator c
      where c.product_id = w.product_id and c.role = 'illustration') as illustrations,
    (select group_concat(g.genre, ', ') from work_genre g
      where g.product_id = w.product_id) as genres
from work w
left join work_stat s on s.product_id = w.product_id;
"""

_SUMMARY_COLUMNS = (
    "site_id",
    "maker_id",
    "work_name",
    "work_name_masked",
    "age_category",
    "work_type",
    "book_type",
    "work_image",
    "regist_date",
    "series",
    "work_url",
)

_DETAIL_COLUMNS = (
    "circle",
    "brand",
    "publisher",
    "label",
    "description",
    "file_size",
    "file_size_bytes",
    "page_count",
    "announce_date",
    "modified_date",
)

_STAT_COLUMNS = (
    "price",
    "price_without_tax",
    "official_price",
    "discount_rate",
    "dl_count",
    "wishlist_count",
    "rate_average",
    "rate_count",
    "review_count",
    "is_sale",
    "is_discount",
)

_HISTORY_COLUMNS = ("price", "dl_count", "wishlist_count", "rate_average", "rate_count", "review_count")


class SchemaVersionError(RuntimeError):
    """The database file was written by an incompatible version."""


def to_iso(value: datetime | None) -> str | None:
    """Render a datetime the way it is stored (``YYYY-MM-DD HH:MM:SS``)."""
    if value is None:
        return None
    return value.isoformat(sep=" ", timespec="seconds")


def from_iso(value: str | None) -> datetime | None:
    """Parse a datetime stored by :func:`to_iso`."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:  # pragma: no cover - defensive
        return None


def _enum(enum_cls: Any, value: Any) -> Any:  # noqa: ANN401 - generic enum helper
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:  # pragma: no cover - defensive
        return None


def work_url(work: Work) -> str:
    """Return the public work page URL for ``work``."""
    return f"https://www.dlsite.com/{work.site_id or 'maniax'}/work/=/product_id/{work.product_id}.html"


def _summary_values(work: Work) -> dict[str, Any]:
    return {
        "site_id": work.site_id,
        "maker_id": work.maker_id,
        "work_name": work.work_name,
        "work_name_masked": work.work_name_masked,
        "age_category": int(work.age_category) if work.age_category is not None else None,
        "work_type": work.work_type.value if work.work_type else None,
        "book_type": work.book_type.value if work.book_type else None,
        "work_image": work.work_image,
        "regist_date": to_iso(work.regist_date),
        "series": work.series,
        "work_url": work_url(work),
    }


def _detail_values(work: Work) -> dict[str, Any]:
    return {
        "circle": work.circle,
        "brand": work.brand,
        "publisher": work.publisher,
        "label": work.label,
        "description": work.description,
        "file_size": work.file_size,
        "file_size_bytes": parse_file_size(work.file_size),
        "page_count": work.page_count,
        "announce_date": to_iso(work.announce_date),
        "modified_date": to_iso(work.modified_date),
    }


class WorkDatabase:
    """SQLite database of DLsite voice works.

    Args:
        path: Database file path. ``:memory:`` is accepted for tests.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("pragma journal_mode = wal")
        self.conn.execute("pragma foreign_keys = on")
        try:
            self._migrate()
        except Exception:
            self.conn.close()
            raise

    def __enter__(self) -> Self:
        """Enter the database context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the database."""
        self.close()

    def close(self) -> None:
        """Close the underlying connection."""
        self.conn.close()

    def _migrate(self) -> None:
        version = int(self.conn.execute("pragma user_version").fetchone()[0])
        if version == 0:
            with self.conn:
                self.conn.executescript(_SCHEMA)
                self.conn.execute(f"pragma user_version = {SCHEMA_VERSION}")
        elif version > SCHEMA_VERSION:
            msg = f"{self.path} was created by a newer dojinvoice-db (schema v{version} > v{SCHEMA_VERSION})"
            raise SchemaVersionError(msg)

    # -- writes ---------------------------------------------------------

    def upsert_work(self, work: Work, *, detail: bool, now: datetime | None = None) -> None:
        """Insert or update ``work``.

        Args:
            work: The work to store.
            detail: Whether ``work`` carries the work-page fields. When false,
                only the cheap ajax-sourced columns are touched, so existing
                detail columns are never overwritten with NULLs.
            now: Timestamp recorded as the fetch time (defaults to now).
        """
        stamp = to_iso(now or datetime.now().astimezone())
        values = _summary_values(work)
        columns = list(_SUMMARY_COLUMNS)
        if detail:
            values |= _detail_values(work)
            columns += [*_DETAIL_COLUMNS, "detail_fetched_at"]
            values["detail_fetched_at"] = stamp
        else:
            columns.append("summary_fetched_at")
            values["summary_fetched_at"] = stamp
        values["product_id"] = work.product_id
        values["first_seen_at"] = stamp
        insert_columns = ["product_id", "first_seen_at", *columns]
        placeholders = ",".join("?" * len(insert_columns))
        updates = ",".join(f"{c} = excluded.{c}" for c in columns)
        with self.conn:
            self.conn.execute(
                f"insert into work ({','.join(insert_columns)}) values ({placeholders}) "  # noqa: S608
                f"on conflict (product_id) do update set {updates}",
                [values[c] for c in insert_columns],
            )
            if detail:
                self._replace_children(work)

    def _replace_children(self, work: Work) -> None:
        pid = work.product_id
        creators = [(pid, role, name) for role in CREATOR_ROLES for name in getattr(work, role, None) or []]
        self.conn.execute("delete from work_creator where product_id = ?", (pid,))
        self.conn.executemany("insert or ignore into work_creator values (?,?,?)", creators)

        for table, column, items in (
            ("work_genre", "genre", work.genre),
            ("work_file_format", "file_format", work.file_format),
            ("work_event", "event", work.event),
        ):
            self.conn.execute(f"delete from {table} where product_id = ?", (pid,))  # noqa: S608
            self.conn.executemany(
                f"insert or ignore into {table} (product_id, {column}) values (?,?)",  # noqa: S608
                [(pid, item) for item in items or []],
            )

        self.conn.execute("delete from work_sample_image where product_id = ?", (pid,))
        self.conn.executemany(
            "insert or ignore into work_sample_image values (?,?,?)",
            [(pid, i, url) for i, url in enumerate(work.sample_images or [])],
        )

    def upsert_stats(self, stats: WorkStats, *, now: datetime | None = None) -> bool:
        """Store ``stats``, appending to the history only when figures changed.

        Returns:
            Whether a history row was appended.
        """
        stamp = to_iso(now or datetime.now().astimezone())
        values = {c: getattr(stats, c) for c in _STAT_COLUMNS}
        previous = self.conn.execute(
            f"select {','.join(_HISTORY_COLUMNS)} from work_stat where product_id = ?",  # noqa: S608
            (stats.product_id,),
        ).fetchone()
        changed = previous is None or any(previous[c] != values[c] for c in _HISTORY_COLUMNS)
        columns = ["product_id", *_STAT_COLUMNS, "fetched_at"]
        placeholders = ",".join("?" * len(columns))
        updates = ",".join(f"{c} = excluded.{c}" for c in (*_STAT_COLUMNS, "fetched_at"))
        with self.conn:
            self.conn.execute(
                f"insert into work_stat ({','.join(columns)}) values ({placeholders}) "  # noqa: S608
                f"on conflict (product_id) do update set {updates}",
                [stats.product_id, *(values[c] for c in _STAT_COLUMNS), stamp],
            )
            if changed:
                self.conn.execute(
                    f"insert into work_stat_history "  # noqa: S608
                    f"(product_id, fetched_at, {','.join(_HISTORY_COLUMNS)}) "
                    f"values ({','.join('?' * (len(_HISTORY_COLUMNS) + 2))})",
                    [stats.product_id, stamp, *(values[c] for c in _HISTORY_COLUMNS)],
                )
        return changed

    def record_error(self, product_id: str, message: str, *, now: datetime | None = None) -> None:
        """Record a failed fetch so later runs can skip or retry it."""
        stamp = to_iso(now or datetime.now().astimezone())
        with self.conn:
            self.conn.execute(
                "insert into fetch_error (product_id, attempts, last_error, last_attempt_at) "
                "values (?, 1, ?, ?) "
                "on conflict (product_id) do update set "
                "attempts = attempts + 1, last_error = excluded.last_error, "
                "last_attempt_at = excluded.last_attempt_at",
                (product_id, message[:500], stamp),
            )

    def clear_error(self, product_id: str) -> None:
        """Forget a previously recorded fetch failure."""
        with self.conn:
            self.conn.execute("delete from fetch_error where product_id = ?", (product_id,))

    def set_state(self, key: str, value: str) -> None:
        """Store a bookkeeping value."""
        with self.conn:
            self.conn.execute(
                "insert into crawl_state (key, value) values (?,?) "
                "on conflict (key) do update set value = excluded.value",
                (key, value),
            )

    def get_state(self, key: str) -> str | None:
        """Read a bookkeeping value."""
        row = self.conn.execute("select value from crawl_state where key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    # -- reads ----------------------------------------------------------

    def known_product_ids(self) -> set[str]:
        """Return every product ID already stored."""
        return {row[0] for row in self.conn.execute("select product_id from work")}

    def count_works(self) -> int:
        """Return the number of stored works."""
        return int(self.conn.execute("select count(*) from work").fetchone()[0])

    def pending_detail_ids(
        self,
        *,
        limit: int | None = None,
        stale_before: datetime | None = None,
        retry_errors: bool = False,
        now: datetime | None = None,
    ) -> list[str]:
        """Return works whose work-page detail should be fetched.

        A work is pending when its detail was never fetched, when it was
        fetched before ``stale_before``, or when it was fetched while the work
        was still an announcement and has since been released -- announced
        works are not re-fetched every run, only once after release.
        """
        conditions = [
            "w.detail_fetched_at is null",
            (
                "(w.regist_date is not null and w.detail_fetched_at is not null"
                " and w.regist_date > w.detail_fetched_at and w.regist_date <= ?)"
            ),
        ]
        params: list[Any] = [to_iso(now or datetime.now().astimezone())]
        if stale_before is not None:
            conditions.append("w.detail_fetched_at < ?")
            params.append(to_iso(stale_before))
        sql = f"select w.product_id from work w where ({' or '.join(conditions)})"  # noqa: S608
        if not retry_errors:
            sql += " and not exists (select 1 from fetch_error e where e.product_id = w.product_id and e.attempts >= ?)"
            params.append(MAX_ERROR_ATTEMPTS)
        sql += " order by w.regist_date desc"
        if limit is not None:
            sql += " limit ?"
            params.append(limit)
        return [row[0] for row in self.conn.execute(sql, params)]

    def stale_stat_ids(self, *, stale_before: datetime | None = None, limit: int | None = None) -> list[str]:
        """Return works whose stats are missing or older than ``stale_before``.

        Ordered oldest-first so an interrupted refresh resumes where it left off.
        """
        sql = "select w.product_id from work w left join work_stat s on s.product_id = w.product_id"
        params: list[Any] = []
        if stale_before is not None:
            sql += " where s.fetched_at is null or s.fetched_at < ?"
            params.append(to_iso(stale_before))
        sql += " order by s.fetched_at is not null, s.fetched_at"
        if limit is not None:
            sql += " limit ?"
            params.append(limit)
        return [row[0] for row in self.conn.execute(sql, params)]

    def load_work(self, product_id: str) -> Work | None:
        """Rebuild a :class:`~dlsite_async.Work` from the stored summary columns.

        Used to fetch a work's detail page on a later run without re-requesting
        the ajax info that produced the row in the first place.
        """
        row = self.conn.execute("select * from work where product_id = ?", (product_id,)).fetchone()
        if row is None:
            return None
        return Work(
            product_id=row["product_id"],
            site_id=row["site_id"] or "maniax",
            maker_id=row["maker_id"],
            work_name=row["work_name"],
            age_category=_enum(AgeCategory, row["age_category"]),
            work_name_masked=row["work_name_masked"],
            work_type=_enum(WorkType, row["work_type"]),
            book_type=_enum(BookType, row["book_type"]),
            work_image=row["work_image"],
            regist_date=from_iso(row["regist_date"]),
            title_name_masked=row["series"],
        )

    def get_work(self, product_id: str) -> dict[str, Any] | None:
        """Return one work with its stats and multi-valued fields, or ``None``."""
        row = self.conn.execute("select * from work where product_id = ?", (product_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        stat = self.conn.execute("select * from work_stat where product_id = ?", (product_id,)).fetchone()
        result["stats"] = dict(stat) if stat else None
        creators: dict[str, list[str]] = {}
        for crow in self.conn.execute(
            "select role, name from work_creator where product_id = ? order by role, rowid",
            (product_id,),
        ):
            creators.setdefault(crow["role"], []).append(crow["name"])
        result["creators"] = creators
        for key, table, column in (
            ("genres", "work_genre", "genre"),
            ("file_formats", "work_file_format", "file_format"),
            ("events", "work_event", "event"),
        ):
            result[key] = [
                r[0]
                for r in self.conn.execute(
                    f"select {column} from {table} where product_id = ? order by rowid",  # noqa: S608
                    (product_id,),
                )
            ]
        result["sample_images"] = [
            r[0]
            for r in self.conn.execute(
                "select url from work_sample_image where product_id = ? order by idx",
                (product_id,),
            )
        ]
        return result

    def summary(self) -> dict[str, Any]:
        """Return aggregate counts for the ``stats`` command."""
        row = self.conn.execute(
            "select count(*) as works,"
            " sum(detail_fetched_at is not null) as detailed,"
            " min(regist_date) as oldest,"
            " max(regist_date) as newest"
            " from work",
        ).fetchone()
        return {
            "works": row["works"],
            "detailed": row["detailed"] or 0,
            "pending_detail": row["works"] - (row["detailed"] or 0),
            "oldest_release": row["oldest"],
            "newest_release": row["newest"],
            "circles": self.conn.execute("select count(distinct maker_id) from work").fetchone()[0],
            "voice_actors": self.conn.execute(
                "select count(distinct name) from work_creator where role = 'voice_actor'",
            ).fetchone()[0],
            "genres": self.conn.execute("select count(distinct genre) from work_genre").fetchone()[0],
            "errors": self.conn.execute("select count(*) from fetch_error").fetchone()[0],
            "last_crawl": self.get_state("last_crawl_at"),
        }

    def top_rows(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run a read-only query and return the rows as dicts."""
        return [dict(row) for row in self.conn.execute(sql, params)]
