from dataclasses import replace

import pytest

from dojinvoice_db.db import WorkDatabase
from dojinvoice_db.dlsite import WorkNotFoundError


class FakeClient:
    """Stand-in for :class:`~dojinvoice_db.dlsite.DlsiteClient`.

    ``pages`` maps a 1-based listing page number to the product IDs on it;
    ``info`` maps a product ID to its ajax entry; ``details`` maps a product ID
    to the extra fields its work page would contribute. IDs missing from
    ``info``/``details`` behave like works DLsite does not serve.
    """

    def __init__(self, pages=None, info=None, details=None):
        self.pages = pages or {}
        self.info = info or {}
        self.details = details or {}
        self.request_count = 0
        self.listing_requests: list[int] = []
        self.info_requests: list[list[str]] = []
        self.detail_requests: list[str] = []

    async def fetch_listing_ids(self, query, page):
        self.listing_requests.append(page)
        self.request_count += 1
        return list(self.pages.get(page, []))

    async def fetch_product_info(self, product_ids):
        self.info_requests.append(list(product_ids))
        self.request_count += 1
        return {pid: self.info[pid] for pid in product_ids if pid in self.info}

    async def fetch_detail(self, work):
        self.detail_requests.append(work.product_id)
        self.request_count += 1
        if work.product_id not in self.details:
            msg = f"no work or announce page for {work.product_id}"
            raise WorkNotFoundError(msg)
        return replace(work, **self.details[work.product_id])

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


def make_info(product_id, **overrides):
    """Build a plausible ``product/info/ajax`` entry."""
    entry = {
        "site_id": "maniax",
        "maker_id": f"RG{product_id[2:]}",
        "work_name": f"作品 {product_id}",
        "age_category": 3,
        "work_type": "SOU",
        "regist_date": "2026-08-01 00:00:00",
        "work_image": f"//img/{product_id}.jpg",
        "price": 550,
        "dl_count": 42,
        "wishlist_count": 7,
        "rate_average_2dp": 4.5,
        "rate_count": 12,
        "review_count": 2,
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def db(tmp_path):
    with WorkDatabase(tmp_path / "test.db") as database:
        yield database


@pytest.fixture
def fake_client_factory():
    return FakeClient
