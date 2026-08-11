import asyncio
import time
from datetime import datetime

import pytest
from aiohttp import ClientResponseError, RequestInfo, ServerTimeoutError
from dlsite_async import AgeCategory, BookType, WorkType
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from dojinvoice_db.dlsite import (
    DlsiteClient,
    WorkNotFoundError,
    _Throttle,
    batched,
    escape_stray_brackets,
    extract_product_ids,
    parse_detail_html,
    work_from_info,
)
from dojinvoice_db.models import SearchQuery

LISTING = """
<ul class="n_worklist">
  <li data-list_item_product_id="RJ01000001" class="search_result_img_box_inner">a</li>
  <li data-list_item_product_id="RJ01000002">b</li>
  <li data-list_item_product_id="RJ01000001">dup</li>
  <li data-list_item_product_id="BJ01000003">book</li>
  <li>no id, and a bare RJ99999999 in the text</li>
</ul>
"""


def test_extract_product_ids_dedupes_and_keeps_order():
    assert extract_product_ids(LISTING) == ["RJ01000001", "RJ01000002", "BJ01000003"]


def test_extract_product_ids_ignores_ids_outside_the_attribute():
    assert "RJ99999999" not in extract_product_ids(LISTING)


def test_extract_product_ids_on_empty_page():
    assert extract_product_ids("<html></html>") == []


def test_work_from_info_maps_enums_and_dates():
    work = work_from_info(
        "RJ01000001",
        {
            "site_id": "maniax",
            "maker_id": "RG1",
            "work_name": "title",
            "age_category": 3,
            "work_type": "SOU",
            "book_type": {"value": "comic"},
            "regist_date": "2025-06-03 00:00:00",
            "title_name_masked": "series",
            "price": 550,
        },
    )
    assert work.product_id == "RJ01000001"
    assert work.age_category is AgeCategory.R18
    assert work.work_type is WorkType.VOICE_ASMR
    assert work.book_type is BookType.BOOK
    assert work.regist_date == datetime(2025, 6, 3)
    assert work.series == "series"


def test_work_from_info_tolerates_unknown_enum_values():
    work = work_from_info(
        "RJ01000001",
        {
            "site_id": "maniax",
            "maker_id": "RG1",
            "work_name": "title",
            "age_category": 99,
            "work_type": "NOPE",
            "book_type": None,
            "regist_date": "not a date",
        },
    )
    assert work.age_category is None
    assert work.work_type is None
    assert work.book_type is None
    assert work.regist_date is None


def test_batched_splits_into_chunks():
    assert [list(c) for c in batched(list("abcde"), 2)] == [["a", "b"], ["c", "d"], ["e"]]
    assert [list(c) for c in batched([], 2)] == []


async def test_fetch_product_info_short_circuits_on_empty_input():
    client = DlsiteClient(interval=0)
    try:
        assert await client.fetch_product_info([]) == {}
        assert client.request_count == 0
    finally:
        await client.close()


async def test_fetch_product_info_ignores_malformed_json(monkeypatch):
    client = DlsiteClient(interval=0)

    async def fake_get_text(url, *, params=None):
        return "<html>error page</html>"

    monkeypatch.setattr(client, "_get_text", fake_get_text)
    try:
        assert await client.fetch_product_info(["RJ1"]) == {}
    finally:
        await client.close()


async def test_fetch_detail_raises_when_neither_page_exists(monkeypatch):
    client = DlsiteClient(interval=0)
    work = work_from_info("RJ1", {"site_id": "maniax", "maker_id": "RG1", "work_name": "t", "age_category": 1})

    async def missing(url, *, params=None):
        return None

    monkeypatch.setattr(client, "_get_text", missing)
    try:
        with pytest.raises(WorkNotFoundError):
            await client.fetch_detail(work)
    finally:
        await client.close()


async def test_fetch_detail_falls_back_to_announce_page(monkeypatch):
    client = DlsiteClient(interval=0)
    work = work_from_info("RJ1", {"site_id": "maniax", "maker_id": "RG1", "work_name": "t", "age_category": 1})
    seen: list[str] = []

    async def fake_get_text(url, *, params=None):
        seen.append(url)
        if "/work/" in url:
            return None
        return '<table id="work_outline"><tr><th>ジャンル</th><td><a>ASMR</a></td></tr></table>'

    monkeypatch.setattr(client, "_get_text", fake_get_text)
    try:
        detailed = await client.fetch_detail(work)
    finally:
        await client.close()
    assert detailed.genre == ["ASMR"]
    assert len(seen) == 2
    assert "/announce/" in seen[1]


def test_escape_stray_brackets_keeps_real_tags():
    html = '<table id="t"><tr><td><a href="/x">y</a><br />z</td></tr></table><!-- c -->'
    assert escape_stray_brackets(html) == html


def test_escape_stray_brackets_escapes_pseudo_tags():
    assert escape_stray_brackets("a < b and <台本、オホ声>") == "a &lt; b and &lt;台本、オホ声>"


def test_parse_detail_html_survives_unescaped_brackets_in_description():
    html = (
        "<html><body>"
        '<table id="work_outline"><tr><th>ジャンル</th><td><a>ASMR</a></td></tr></table>'
        "<div>◆4.<JKの家に訪問、いちゃいちゃ、同時絶頂&潮吹き></div>"
        "</body></html>"
    )
    assert parse_detail_html(html)["genre"] == ["ASMR"]


class FakeResponse:
    def __init__(self, text):
        self._text = text

    async def text(self):
        return self._text


class FakeGet:
    """Callable standing in for ``ClientSession.get``, replaying ``outcomes``."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.urls: list[str] = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        return self

    async def __aenter__(self):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    async def __aexit__(self, *_):
        return None


def http_error(status):
    url = URL("https://example.invalid/")
    request_info = RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
    return ClientResponseError(request_info, (), status=status)


@pytest.fixture
def no_sleep(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return slept


async def test_throttle_spaces_requests():
    throttle = _Throttle(0.05)
    start = time.monotonic()
    for _ in range(3):
        await throttle.wait()
    assert time.monotonic() - start >= 0.1


async def test_throttle_is_a_noop_when_disabled():
    throttle = _Throttle(0)
    start = time.monotonic()
    await throttle.wait()
    assert time.monotonic() - start < 0.05


async def test_get_text_counts_requests_and_returns_body(monkeypatch):
    client = DlsiteClient(interval=0)
    monkeypatch.setattr(client.api, "get", FakeGet(["body"]))
    try:
        assert await client._get_text("https://example.invalid/") == "body"
        assert client.request_count == 1
    finally:
        await client.close()


async def test_get_text_returns_none_on_missing_pages(monkeypatch):
    client = DlsiteClient(interval=0)
    monkeypatch.setattr(client.api, "get", FakeGet([http_error(404)]))
    try:
        assert await client._get_text("https://example.invalid/") is None
    finally:
        await client.close()


async def test_get_text_reraises_unexpected_client_errors(monkeypatch):
    client = DlsiteClient(interval=0)
    monkeypatch.setattr(client.api, "get", FakeGet([http_error(401)]))
    try:
        with pytest.raises(ClientResponseError):
            await client._get_text("https://example.invalid/")
    finally:
        await client.close()


async def test_get_text_retries_transient_failures(monkeypatch, no_sleep):
    client = DlsiteClient(interval=0, retries=3)
    fake = FakeGet([http_error(503), ServerTimeoutError(), "body"])
    monkeypatch.setattr(client.api, "get", fake)
    try:
        assert await client._get_text("https://example.invalid/") == "body"
    finally:
        await client.close()
    assert fake.calls == 3
    assert no_sleep == [1.0, 2.0]


async def test_get_text_gives_up_after_the_retry_budget(monkeypatch, no_sleep):
    client = DlsiteClient(interval=0, retries=2)
    monkeypatch.setattr(client.api, "get", FakeGet([http_error(503), http_error(503)]))
    try:
        with pytest.raises(WorkNotFoundError):
            await client._get_text("https://example.invalid/")
    finally:
        await client.close()


async def test_fetch_listing_ids_parses_the_page(monkeypatch):
    client = DlsiteClient(interval=0)
    fake = FakeGet([LISTING])
    monkeypatch.setattr(client.api, "get", fake)
    try:
        ids = await client.fetch_listing_ids(SearchQuery(), 2)
    finally:
        await client.close()
    assert ids == ["RJ01000001", "RJ01000002", "BJ01000003"]
    assert fake.urls[0].endswith("/page/2")


async def test_fetch_listing_ids_returns_empty_beyond_the_last_page(monkeypatch):
    client = DlsiteClient(interval=0)
    monkeypatch.setattr(client.api, "get", FakeGet([http_error(404)]))
    try:
        assert await client.fetch_listing_ids(SearchQuery(), 999) == []
    finally:
        await client.close()


async def test_fetch_product_info_parses_batched_json(monkeypatch):
    client = DlsiteClient(interval=0)
    fake = FakeGet(['{"RJ1": {"price": 100}, "RJ2": null}'])
    monkeypatch.setattr(client.api, "get", fake)
    try:
        assert await client.fetch_product_info(["RJ1", "RJ2"]) == {"RJ1": {"price": 100}}
    finally:
        await client.close()
