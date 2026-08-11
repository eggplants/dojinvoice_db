from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from dlsite_async import AgeCategory, Work, WorkType

from dojinvoice_db.db import MAX_ERROR_ATTEMPTS, SchemaVersionError, WorkDatabase
from dojinvoice_db.models import WorkStats

NOW = datetime(2026, 8, 11, 12, 0, 0)


def summary_work(product_id="RJ1", **kwargs):
    work = Work(
        product_id=product_id,
        site_id="maniax",
        maker_id="RG1",
        work_name="作品",
        age_category=AgeCategory.R18,
        work_type=WorkType.VOICE_ASMR,
        regist_date=datetime(2026, 8, 1),
        work_image="//img/x.jpg",
    )
    return replace(work, **kwargs) if kwargs else work


def detailed_work(product_id="RJ1", **kwargs):
    return summary_work(
        product_id,
        circle="サークル",
        description="説明",
        file_size="1.5GB",
        genre=["ASMR", "耳舐め"],
        voice_actor=["声優A", "声優B"],
        scenario=["書き手"],
        file_format=["WAV"],
        event=["イベント"],
        sample_images=["//img/1.jpg", "//img/2.jpg"],
        **kwargs,
    )


def test_creates_schema_and_is_reopenable(tmp_path):
    path = tmp_path / "nested" / "test.db"
    with WorkDatabase(path) as db:
        db.upsert_work(summary_work(), detail=False, now=NOW)
    with WorkDatabase(path) as db:
        assert db.count_works() == 1


def test_rejects_future_schema_versions(tmp_path):
    path = tmp_path / "test.db"
    with WorkDatabase(path) as db:
        db.conn.execute("pragma user_version = 999")
        db.conn.commit()
    with pytest.raises(SchemaVersionError):
        WorkDatabase(path)


def test_summary_upsert_does_not_clobber_detail(db):
    db.upsert_work(detailed_work(), detail=True, now=NOW)
    db.upsert_work(summary_work(work_name="改題"), detail=False, now=NOW + timedelta(days=1))
    row = db.get_work("RJ1")
    assert row["work_name"] == "改題"
    assert row["circle"] == "サークル"
    assert row["description"] == "説明"
    assert row["detail_fetched_at"] is not None


def test_first_seen_at_is_preserved_across_updates(db):
    db.upsert_work(summary_work(), detail=False, now=NOW)
    db.upsert_work(summary_work(), detail=False, now=NOW + timedelta(days=5))
    row = db.get_work("RJ1")
    assert row["first_seen_at"] == "2026-08-11 12:00:00"
    assert row["summary_fetched_at"] == "2026-08-16 12:00:00"


def test_detail_upsert_stores_child_rows(db):
    db.upsert_work(detailed_work(), detail=True, now=NOW)
    row = db.get_work("RJ1")
    assert row["creators"]["voice_actor"] == ["声優A", "声優B"]
    assert row["creators"]["scenario"] == ["書き手"]
    assert row["genres"] == ["ASMR", "耳舐め"]
    assert row["file_formats"] == ["WAV"]
    assert row["events"] == ["イベント"]
    assert row["sample_images"] == ["//img/1.jpg", "//img/2.jpg"]
    assert row["file_size_bytes"] == 1_500_000_000


def test_detail_upsert_replaces_stale_child_rows(db):
    db.upsert_work(detailed_work(), detail=True, now=NOW)
    db.upsert_work(
        replace(detailed_work(), voice_actor=["声優C"], genre=[]),
        detail=True,
        now=NOW + timedelta(days=1),
    )
    row = db.get_work("RJ1")
    assert row["creators"]["voice_actor"] == ["声優C"]
    assert row["genres"] == []


def test_get_work_returns_none_for_unknown_id(db):
    assert db.get_work("RJ404") is None


def test_load_work_roundtrips_summary_fields(db):
    db.upsert_work(summary_work(), detail=False, now=NOW)
    loaded = db.load_work("RJ1")
    assert loaded.product_id == "RJ1"
    assert loaded.maker_id == "RG1"
    assert loaded.age_category is AgeCategory.R18
    assert loaded.work_type is WorkType.VOICE_ASMR
    assert loaded.regist_date == datetime(2026, 8, 1)
    assert db.load_work("RJ404") is None


def test_stats_history_only_grows_when_figures_change(db):
    db.upsert_work(summary_work(), detail=False, now=NOW)
    stats = WorkStats(product_id="RJ1", price=550, dl_count=10)
    assert db.upsert_stats(stats, now=NOW) is True
    assert db.upsert_stats(stats, now=NOW + timedelta(days=1)) is False
    assert db.upsert_stats(WorkStats(product_id="RJ1", price=550, dl_count=11), now=NOW + timedelta(days=2)) is True
    history = db.top_rows("select fetched_at, dl_count from work_stat_history order by fetched_at")
    assert [row["dl_count"] for row in history] == [10, 11]
    assert db.get_work("RJ1")["stats"]["dl_count"] == 11


def test_pending_detail_ids_lists_only_undetailed_works(db):
    db.upsert_work(summary_work("RJ1"), detail=False, now=NOW)
    db.upsert_work(detailed_work("RJ2"), detail=True, now=NOW)
    assert db.pending_detail_ids(now=NOW) == ["RJ1"]


def test_pending_detail_ids_refetches_released_announcements(db):
    announced = detailed_work("RJ3", regist_date=datetime(2026, 9, 1))
    db.upsert_work(announced, detail=True, now=NOW)
    # Still unreleased: leave it alone.
    assert db.pending_detail_ids(now=NOW) == []
    # Released since the detail was fetched: fetch it once more.
    assert db.pending_detail_ids(now=datetime(2026, 9, 2)) == ["RJ3"]


def test_pending_detail_ids_honours_stale_before_and_limit(db):
    db.upsert_work(detailed_work("RJ1"), detail=True, now=NOW - timedelta(days=30))
    db.upsert_work(detailed_work("RJ2"), detail=True, now=NOW)
    assert db.pending_detail_ids(stale_before=NOW - timedelta(days=7), now=NOW) == ["RJ1"]
    assert db.pending_detail_ids(stale_before=NOW, limit=1, now=NOW) in (["RJ1"], ["RJ2"])


def test_pending_detail_ids_skips_repeatedly_failing_works(db):
    db.upsert_work(summary_work("RJ1"), detail=False, now=NOW)
    for _ in range(MAX_ERROR_ATTEMPTS):
        db.record_error("RJ1", "boom", now=NOW)
    assert db.pending_detail_ids(now=NOW) == []
    assert db.pending_detail_ids(retry_errors=True, now=NOW) == ["RJ1"]
    db.clear_error("RJ1")
    assert db.pending_detail_ids(now=NOW) == ["RJ1"]


def test_stale_stat_ids_orders_missing_first(db):
    db.upsert_work(summary_work("RJ1"), detail=False, now=NOW)
    db.upsert_work(summary_work("RJ2"), detail=False, now=NOW)
    db.upsert_stats(WorkStats(product_id="RJ2", price=100), now=NOW)
    assert db.stale_stat_ids() == ["RJ1", "RJ2"]
    assert db.stale_stat_ids(stale_before=NOW - timedelta(days=1)) == ["RJ1"]
    assert db.stale_stat_ids(limit=1) == ["RJ1"]


def test_state_roundtrip(db):
    assert db.get_state("last_crawl_at") is None
    db.set_state("last_crawl_at", "2026-08-11")
    db.set_state("last_crawl_at", "2026-08-12")
    assert db.get_state("last_crawl_at") == "2026-08-12"


def test_summary_counts(db):
    db.upsert_work(detailed_work("RJ1"), detail=True, now=NOW)
    db.upsert_work(summary_work("RJ2", maker_id="RG2"), detail=False, now=NOW)
    db.record_error("RJ9", "boom", now=NOW)
    summary = db.summary()
    assert summary["works"] == 2
    assert summary["detailed"] == 1
    assert summary["pending_detail"] == 1
    assert summary["circles"] == 2
    assert summary["voice_actors"] == 2
    assert summary["genres"] == 2
    assert summary["errors"] == 1


def test_known_product_ids(db):
    db.upsert_work(summary_work("RJ1"), detail=False, now=NOW)
    db.upsert_work(summary_work("RJ2"), detail=False, now=NOW)
    assert db.known_product_ids() == {"RJ1", "RJ2"}
