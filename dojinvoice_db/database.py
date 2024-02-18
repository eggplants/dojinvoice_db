from __future__ import annotations

import logging
from sqlite3 import Error, connect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .parser import DlsiteDict


class DojinvoiceDatabase:
    def __init__(self, db_filepath: str, log: str = ".log") -> None:
        """Init."""
        self.db_filepath = db_filepath
        f = logging.FileHandler(log)
        f.setLevel(logging.DEBUG)
        self.__init_database()

    def __init_database(self) -> None:
        """Create a db file and tables if not exists."""
        connect(self.db_filepath)

    def __connect_db(self, sql: str, p: list[tuple[Any, ...]] | None = None) -> None:
        """Connect to the database and execute the SQL."""
        conn = None
        try:
            conn = connect(self.db_filepath)

            c = conn.cursor()
            if p is None:
                c.execute(sql)
            else:
                c.executemany(sql, p)

            conn.commit()
        except Error as e:
            msg = str(e)
            if msg[0:5] == "table" and msg[-14:] == "already exists":
                pass
            else:
                logging.exception("[DB Error]: {e}")
                logging.exception("- [SQL]: {sql}")
                logging.exception("- [Return]: {p}")
        finally:
            if conn:
                conn.close()

    def get_work_ids(self) -> list[str]:
        conn = connect(self.db_filepath)
        c = conn.cursor().execute("select work_id from work")
        res = [i[0] for i in c]
        conn.close()
        return res

    def __create_table(self, schema: str) -> None:
        self.__connect_db("create table " + schema)

    def create_tables(self) -> None:
        """Create the tables."""

        self.__create_table(
            """work (
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
                ) """,
        )
        self.__create_table(
            """option (
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
                ) """,
        )
        self.__create_table(
            """writer (
                    work_id text,
                    writer text,
                    primary key (work_id, writer)
                ) """,
        )
        self.__create_table(
            """scenario (
                    work_id text,
                    scenario text,
                    primary key (work_id, scenario)
                ) """,
        )
        self.__create_table(
            """illustrator (
                    work_id text,
                    illustrator text,
                    primary key (work_id, illustrator)
                ) """,
        )
        self.__create_table(
            """voice (
                    work_id text,
                    voice text,
                    primary key (work_id, voice)
                ) """,
        )
        self.__create_table(
            """musician (
                    work_id text,
                    musician text,
                    primary key (work_id, musician)
                ) """,
        )
        self.__create_table(
            """genre (
                    work_id text,
                    genre text,
                    primary key (work_id, genre)
                ) """,
        )

    def push(self, data: list[DlsiteDict]) -> None:
        """Insert data to the database."""
        work_data: list[tuple[Any, ...]] = []
        option_data: list[tuple[Any, ...]] = []
        writer_data: list[tuple[Any, ...]] = []
        scenario_data: list[tuple[Any, ...]] = []
        illustrator_data: list[tuple[Any, ...]] = []
        voice_data: list[tuple[Any, ...]] = []
        musician_data: list[tuple[Any, ...]] = []
        genre_data: list[tuple[Any, ...]] = []
        for datum in data:
            work_data.append(
                (
                    datum["work_id"],
                    datum["detail_link"],
                    datum["title"],
                    datum["circle"],
                    datum["circle_link"],
                    datum["category"],
                    datum["sale_date"],
                    datum["age_zone"],
                    datum["file_format"],
                    datum["file_size"],
                    datum["description"],
                    datum["monopoly"],
                    datum["price"],
                ),
            )

            option_data.append(
                (
                    datum["work_id"],
                    datum["thumbnail"],
                    datum["cien_link"],
                    datum["series"],
                    datum["chobit_link"],
                    datum["sales"],
                    datum["favorites"],
                    datum["trial_link"],
                    datum["trial_size"],
                    datum["rating"],
                ),
            )

            if datum["writers"] is not None:
                writer_data.extend([(datum["work_id"], writer) for writer in datum["writers"]])

            if datum["voices"] is not None:
                voice_data.extend([(datum["work_id"], voice) for voice in datum["voices"]])

            if datum["scenarios"] is not None:
                scenario_data.extend([(datum["work_id"], scenario) for scenario in datum["scenarios"]])

            if datum["illustrators"] is not None:
                illustrator_data.extend([(datum["work_id"], illustrator) for illustrator in datum["illustrators"]])

            if datum["musicians"] is not None:
                musician_data.extend([(datum["work_id"], musician) for musician in datum["musicians"]])

            if datum["genres"] is not None:
                genre_data.extend([(datum["work_id"], genre) for genre in datum["genres"]])

        query_lists: list[tuple[str, list[tuple[Any, ...]]]] = [
            ("insert into work values (?,?,?,?,?,?,?,?,?,?,?,?,?)", work_data),
            ("insert into option values (?,?,?,?,?,?,?,?,?,?)", option_data),
            ("insert into writer values (?,?)", writer_data),
            ("insert into scenario values (?,?)", scenario_data),
            ("insert into illustrator values (?,?)", illustrator_data),
            ("insert into voice values (?,?)", voice_data),
            ("insert into musician values (?,?)", musician_data),
            ("insert into genre values (?,?)", genre_data),
        ]

        for query, data_list in query_lists:
            unique_data_list = list(set(data_list))
            if len(unique_data_list) != 0:
                self.__connect_db(query, unique_data_list)
