# dojinvoice_db

[![Release Package](
  <https://github.com/eggplants/dojinvoice_db/workflows/Release%20Package/badge.svg>
)](
  <https://github.com/eggplants/dojinvoice_db/actions/runs/355419760>
) [![pre-commit.ci status](
  <https://results.pre-commit.ci/badge/github/eggplants/dojinvoice_db/main.svg>
)](
  <https://results.pre-commit.ci/latest/github/eggplants/dojinvoice_db/main>
)

[![PyPI version](
  <https://badge.fury.io/py/dojinvoice-db.svg>
)](
  <https://badge.fury.io/py/dojinvoice_db>
) [![Maintainability](
  <https://qlty.sh/badges/0c15ff3a-7972-4c90-a7a9-de4299ba05e5/maintainability.svg>
  )](
  <https://qlty.sh/gh/eggplants/projects/dojinvoice_db>
) [![MIT License](
  <http://img.shields.io/badge/license-MIT-blue.svg?style=flat>
)](LICENSE) [![Code Coverage](
  <https://qlty.sh/badges/0c15ff3a-7972-4c90-a7a9-de4299ba05e5/test_coverage.svg>
  )](
  <https://qlty.sh/gh/eggplants/projects/dojinvoice_db>
)

Dojinvoice (同人音声) DB

- DLsite
  - <https://www.dlsite.com/maniax/works/voice>

## How to run

```bash
pip install dojinvoice-db
```

```shellsession
$ dvdb
Download pages? >> (`y` or Enter)
<int> work(s) have already been committed to existing db!
Now: ./dlsite/00001.html
Now: ./dlsite/00002.html
Now: ./dlsite/00003.html
...
```

## DB Schema

```python
create_table(
    '''work (
            work_id text primary key,
            detail_link text not null,
            title text not null,
            circle text not null,
            circle_link text not null,
            category text not null,
            sale_date integer not null,
            age_zone text not null,
            file_format text not null,
            file_size text not null,
            description str not null,
            monopoly integer not null,
            price integer not null
        ) '''
)
create_table(
    '''option (
            work_id text primary key,
            thumbnail text,
            cien_link text,
            series text,
            chobit_link text,
            sales integer,
            favorites integer,
            trial_link text,
            trial_size integer,
            rating real
        ) '''
)
create_table(
    '''writer (
            work_id text,
            writer text,
            primary key (work_id, writer)
        ) '''
)
create_table(
    '''scenario (
            work_id text,
            scenario text,
            primary key (work_id, scenario)
        ) '''
)
create_table(
    '''illustrator (
            work_id text,
            illustrator text,
            primary key (work_id, illustrator)
        ) '''
)
create_table(
    '''voice (
            work_id text,
            voice text,
            primary key (work_id, voice)
        ) '''
)
create_table(
    '''musician (
            work_id text,
            musician text,
            primary key (work_id, musician)
        ) '''
)
create_table(
    '''genre (
            work_id text,
            genre text,
            primary key (work_id, genre)
        ) '''
)
```
