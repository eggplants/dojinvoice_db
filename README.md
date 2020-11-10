# dojinvoice_db

- 同人音声DB
  - DLsite

## スキーマ

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