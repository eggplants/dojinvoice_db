from dojinvoice_db.models import SearchQuery, WorkStats, parse_file_size


def test_parse_file_size_handles_dlsite_labels():
    assert parse_file_size("215.78MB") == 215_780_000
    assert parse_file_size("総計 1.2GB") == 1_200_000_000
    assert parse_file_size("1,024KB") == 1_024_000
    assert parse_file_size("") is None
    assert parse_file_size(None) is None
    assert parse_file_size("不明") is None


def test_page_url_encodes_indexed_params():
    url = SearchQuery().page_url(3)
    assert url.startswith("https://www.dlsite.com/maniax/fsr/=/")
    assert "sex_category%5B0%5D/male" in url
    assert "work_category%5B0%5D/doujin" in url
    assert "work_type%5B0%5D/SOU" in url
    assert "order%5B0%5D/release_d" in url
    assert url.endswith("/per_page/100/page/3")


def test_page_url_repeats_multi_valued_params():
    url = SearchQuery(sex_category=("male", "female")).page_url(1)
    assert "sex_category%5B0%5D/male" in url
    assert "sex_category%5B1%5D/female" in url


def test_describe_is_stable():
    assert SearchQuery().describe() == "maniax:male/doujin/SOU/release_d"


def test_work_stats_from_info_coerces_types():
    stats = WorkStats.from_info(
        "RJ1",
        {
            "price": "550",
            "dl_count": 12,
            "rate_average_2dp": 4.59,
            "rate_count": None,
            "is_sale": 1,
            "wishlist_count": "bogus",
        },
    )
    assert stats == WorkStats(
        product_id="RJ1",
        price=550,
        dl_count=12,
        rate_average=4.59,
        rate_count=None,
        is_sale=True,
        wishlist_count=None,
    )
