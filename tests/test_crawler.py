from datetime import datetime, timedelta

from conftest import FakeClient, make_info

from dojinvoice_db import crawler
from dojinvoice_db.crawler import CrawlSession
from dojinvoice_db.models import CrawlOptions

DETAIL = {"circle": "サークル", "genre": ["ASMR"], "voice_actor": ["声優A"], "description": "説明"}


def session(db, client, **kwargs):
    return CrawlSession(db=db, client=client, options=CrawlOptions(interval=0, concurrency=2, **kwargs))


def client_with(page_ids, *, details_for=None):
    ids = [pid for page in page_ids.values() for pid in page]
    detail_ids = ids if details_for is None else details_for
    return FakeClient(
        pages=page_ids,
        info={pid: make_info(pid) for pid in ids},
        details=dict.fromkeys(detail_ids, DETAIL),
    )


async def test_discover_stops_after_known_pages(db):
    client = client_with({1: ["RJ1", "RJ2"], 2: ["RJ3"], 3: ["RJ4"], 4: ["RJ5"]})
    # Pretend pages 2 and 3 were already crawled.
    await crawler.store_summaries(session(db, client), ["RJ3", "RJ4"])
    client.info_requests.clear()

    run = session(db, client, stop_after_known_pages=2)
    found = await crawler.discover_ids(run)

    assert found == ["RJ1", "RJ2"]
    # Pages 2 and 3 hold nothing new, so page 4 is never requested.
    assert client.listing_requests == [1, 2, 3]
    assert run.result.pages_fetched == 3
    assert run.result.ids_seen == 4


async def test_discover_full_reads_until_the_listing_ends(db):
    client = client_with({1: ["RJ1"], 2: ["RJ2"]})
    assert await crawler.discover_ids(session(db, client, full=True)) == ["RJ1", "RJ2"]
    assert client.listing_requests == [1, 2, 3]


async def test_discover_respects_limit_and_max_pages(db):
    client = client_with({1: ["RJ1", "RJ2", "RJ3"], 2: ["RJ4"]})
    assert await crawler.discover_ids(session(db, client, limit=2)) == ["RJ1", "RJ2"]
    assert client.listing_requests == [1]

    client = client_with({1: ["RJ1"], 2: ["RJ2"], 3: ["RJ3"]})
    await crawler.discover_ids(session(db, client, max_pages=2, full=True))
    assert client.listing_requests == [1, 2]


async def test_discover_skips_ids_already_stored(db):
    client = client_with({1: ["RJ1", "RJ2"]})
    await crawler.store_summaries(session(db, client), ["RJ1"])
    assert await crawler.discover_ids(session(db, client, full=True)) == ["RJ2"]


async def test_store_summaries_batches_requests(db):
    ids = [f"RJ{i}" for i in range(5)]
    client = client_with({1: ids})
    run = session(db, client, info_batch=2)
    await crawler.store_summaries(run, ids)
    assert [len(chunk) for chunk in client.info_requests] == [2, 2, 1]
    assert run.result.summaries_written == 5
    assert db.count_works() == 5
    assert db.get_work("RJ0")["stats"]["dl_count"] == 42


async def test_store_summaries_records_unavailable_works(db):
    client = FakeClient(info={"RJ1": make_info("RJ1")})
    run = session(db, client)
    await crawler.store_summaries(run, ["RJ1", "RJ404"])
    assert run.result.summaries_written == 1
    assert run.result.errors == 1
    assert db.top_rows("select product_id, attempts from fetch_error") == [{"product_id": "RJ404", "attempts": 1}]


async def test_fetch_details_stores_detail_fields(db):
    client = client_with({1: ["RJ1"]})
    await crawler.store_summaries(session(db, client), ["RJ1"])
    run = session(db, client)
    await crawler.fetch_details(run, ["RJ1"])
    row = db.get_work("RJ1")
    assert run.result.details_fetched == 1
    assert row["circle"] == "サークル"
    assert row["creators"]["voice_actor"] == ["声優A"]
    assert row["detail_fetched_at"] is not None


async def test_fetch_details_records_failures_without_aborting(db):
    client = client_with({1: ["RJ1", "RJ2"]}, details_for=["RJ2"])
    await crawler.store_summaries(session(db, client), ["RJ1", "RJ2"])
    run = session(db, client)
    await crawler.fetch_details(run, ["RJ1", "RJ2"])
    assert run.result.details_fetched == 1
    assert run.result.errors == 1
    assert db.get_work("RJ2")["circle"] == "サークル"
    assert db.top_rows("select product_id from fetch_error") == [{"product_id": "RJ1"}]


async def test_fetch_details_is_a_noop_for_an_empty_list(db):
    client = FakeClient()
    await crawler.fetch_details(session(db, client), [])
    assert client.request_count == 0


async def test_crawl_runs_all_three_stages(db):
    client = client_with({1: ["RJ1", "RJ2"]})
    result = await crawler.crawl(session(db, client, full=True))
    assert result.new_ids == 2
    assert result.summaries_written == 2
    assert result.details_fetched == 2
    assert sorted(client.detail_requests) == ["RJ1", "RJ2"]
    assert db.get_state("last_crawl_at") is not None
    assert db.get_state("last_query") == "maniax:male/doujin/SOU/release_d"


async def test_second_crawl_only_touches_new_works(db):
    client = client_with({1: ["RJ1"]})
    await crawler.crawl(session(db, client, full=True))

    client.pages[1] = ["RJ2", "RJ1"]
    client.info["RJ2"] = make_info("RJ2")
    client.details["RJ2"] = DETAIL
    client.detail_requests.clear()

    result = await crawler.crawl(session(db, client))
    assert result.new_ids == 1
    assert client.detail_requests == ["RJ2"]


async def test_crawl_resumes_details_left_over_from_an_interrupted_run(db):
    client = client_with({1: ["RJ1", "RJ2"]})
    await crawler.crawl(session(db, client, full=True, skip_details=True))
    assert client.detail_requests == []
    assert db.count_works() == 2

    result = await crawler.crawl(session(db, client))
    assert result.new_ids == 0
    assert sorted(client.detail_requests) == ["RJ1", "RJ2"]


async def test_crawl_does_not_refetch_an_unreleased_announcement(db):
    future = (datetime.now().astimezone() + timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
    client = client_with({1: ["RJ1"]})
    client.info["RJ1"] = make_info("RJ1", regist_date=future)
    await crawler.crawl(session(db, client, full=True))
    assert client.detail_requests == ["RJ1"]

    await crawler.crawl(session(db, client, full=True))
    assert client.detail_requests == ["RJ1"]


async def test_pending_detail_ids_applies_the_stale_window(db):
    client = client_with({1: ["RJ1"]})
    await crawler.crawl(session(db, client, full=True))
    assert crawler.pending_detail_ids(session(db, client)) == []
    # -1 day puts the staleness cutoff in the future, so everything counts as stale.
    assert crawler.pending_detail_ids(session(db, client, detail_stale_days=-1)) == ["RJ1"]


async def test_refresh_stats_updates_figures_and_history(db):
    client = client_with({1: ["RJ1", "RJ2"]})
    await crawler.store_summaries(session(db, client), ["RJ1", "RJ2"])
    client.info["RJ1"] = make_info("RJ1", dl_count=100, price=880)

    updated, missing = await crawler.refresh_stats(session(db, client), ["RJ1", "RJ2", "RJ404"])

    assert (updated, missing) == (2, 1)
    assert client.info_requests[-1] == ["RJ1", "RJ2", "RJ404"]
    stats = db.get_work("RJ1")["stats"]
    assert (stats["dl_count"], stats["price"]) == (100, 880)
    assert len(db.top_rows("select * from work_stat_history where product_id = 'RJ1'")) == 2
