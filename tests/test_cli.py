import json

import pytest
from conftest import FakeClient, make_info

from dojinvoice_db import cli
from dojinvoice_db.db import WorkDatabase

DETAIL = {
    "circle": "サークル",
    "genre": ["ASMR", "耳舐め"],
    "voice_actor": ["声優A"],
    "description": "説明文",
    "file_size": "1.5GB",
    "file_format": ["WAV"],
}


@pytest.fixture
def stub_client(monkeypatch):
    """Replace the real HTTP client with a fake one and hand it to the test."""
    client = FakeClient(
        pages={1: ["RJ1", "RJ2"]},
        info={"RJ1": make_info("RJ1"), "RJ2": make_info("RJ2")},
        details={"RJ1": DETAIL, "RJ2": DETAIL},
    )
    monkeypatch.setattr(cli, "_client", lambda _args: client)
    return client


@pytest.fixture
def populated_db(tmp_path, stub_client):
    path = tmp_path / "test.db"
    assert cli.main(["crawl", "--db", str(path), "--full", "--interval", "0", "-q"]) == 0
    return path


def test_version_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("dvdb ")


def test_no_subcommand_is_an_error():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_crawl_creates_the_database(tmp_path, stub_client, capsys):
    path = tmp_path / "nested" / "voice.db"
    assert cli.main(["crawl", "--db", str(path), "--full", "--interval", "0"]) == 0
    assert "2 new" in capsys.readouterr().out
    with WorkDatabase(path) as db:
        assert db.count_works() == 2
        work = db.get_work("RJ1")
    assert work is not None
    assert work["circle"] == "サークル"


def test_crawl_skip_details_leaves_work_pages_for_later(tmp_path, stub_client):
    path = tmp_path / "test.db"
    assert cli.main(["crawl", "--db", str(path), "--full", "--skip-details", "-q"]) == 0
    assert stub_client.detail_requests == []
    with WorkDatabase(path) as db:
        assert db.pending_detail_ids() == ["RJ1", "RJ2"]

    assert cli.main(["details", "--db", str(path), "-q"]) == 0
    assert sorted(stub_client.detail_requests) == ["RJ1", "RJ2"]


def test_crawl_is_a_no_op_when_nothing_is_new(populated_db, stub_client, capsys):
    stub_client.detail_requests.clear()
    assert cli.main(["crawl", "--db", str(populated_db), "--interval", "0"]) == 0
    assert stub_client.detail_requests == []
    assert "0 new" in capsys.readouterr().out


def test_refresh_updates_stats(populated_db, stub_client, capsys):
    stub_client.info["RJ1"] = make_info("RJ1", dl_count=999)
    assert cli.main(["refresh", "--db", str(populated_db), "--all"]) == 0
    assert "2 updated" in capsys.readouterr().out
    with WorkDatabase(populated_db) as db:
        work = db.get_work("RJ1")
    assert work is not None
    assert work["stats"]["dl_count"] == 999


def test_show_prints_a_work(populated_db, capsys):
    assert cli.main(["show", "--db", str(populated_db), "rj1"]) == 0
    out = capsys.readouterr().out
    assert "RJ1" in out
    assert "サークル" in out
    assert "声優A" in out
    assert "説明文" in out


def test_show_json(populated_db, capsys):
    assert cli.main(["show", "--db", str(populated_db), "RJ1", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["product_id"] == "RJ1"
    assert data["creators"]["voice_actor"] == ["声優A"]
    assert data["stats"]["price"] == 550


def test_show_unknown_work(populated_db, capsys):
    assert cli.main(["show", "--db", str(populated_db), "RJ404"]) == 1
    assert "not in" in capsys.readouterr().err


def test_stats_text_and_json(populated_db, capsys):
    assert cli.main(["stats", "--db", str(populated_db)]) == 0
    out = capsys.readouterr().out
    assert "works" in out
    assert "Top voice actors" in out

    assert cli.main(["stats", "--db", str(populated_db), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["works"] == 2
    assert data["top"]["voice_actors"][0] == {"name": "声優A", "works": 2}


def test_schema_version_error_is_reported(tmp_path, capsys):
    path = tmp_path / "test.db"
    with WorkDatabase(path) as db:
        db.conn.execute("pragma user_version = 999")
        db.conn.commit()
    assert cli.main(["stats", "--db", str(path)]) == 1
    assert "newer dojinvoice-db" in capsys.readouterr().err


def test_keyboard_interrupt_is_reported_as_130(tmp_path, monkeypatch, capsys):
    def boom(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "cmd_stats", boom)
    assert cli.main(["stats", "--db", str(tmp_path / "x.db")]) == 130
    assert "aborted" in capsys.readouterr().err


def test_query_args_build_the_search_query():
    args = cli.build_parser().parse_args(
        [
            "crawl",
            "--sex-category",
            "male",
            "--sex-category",
            "female",
            "--work-type",
            "MUS",
            "--per-page",
            "50",
        ],
    )
    query = cli._query_from_args(args)
    assert query.sex_category == ("male", "female")
    assert query.work_type == ("MUS",)
    assert query.per_page == 50
