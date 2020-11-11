from sqlite3 import Error, connect
from sys import stderr
from typing import Any, Callable, Iterable, List, Union

from .parser import DlsiteDict, DmmDict

DatasDict = List[Union[DlsiteDict, DmmDict]]


class DojinvoiceDatabase(object):
    def __init__(self, db_filepath: str, log: str = 'log') -> None:
        """Init."""
        self.db_filepath = db_filepath
        self.log = open(log, 'w')
        self.__init_database()

    def __init_database(self) -> None:
        """Create a db file and tables if not exists."""
        connect(self.db_filepath)

    def __connect_db(self, sql: str,
                     p: Iterable[Iterable[str]] = tuple()) -> None:
        """Connect to the database and execute the SQL."""
        conn = None
        try:
            conn = connect(self.db_filepath)
            call_func: Callable[[str], None] = lambda _:\
                print(_, file=self.log)
            conn.set_trace_callback(call_func)

            c = conn.cursor()
            if not p:
                c.execute(sql)
            else:
                c.executemany(sql, p)

            conn.commit()
        except Error as e:
            print(e, file=stderr)
            print(sql, file=stderr)
            print(p, file=stderr)
        finally:
            if conn:
                conn.close()

    def create_tables(self) -> None:
        """Create the tables."""
        create_table: Callable[[str], None] = lambda schema:\
            self.__connect_db('create table ' + schema)

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

    def push(self, datas: List[DlsiteDict]) -> None:
        """Insert data to the database."""
        work_data, option_data = [], []
        writer_data, scenario_data, illustrator_data = [], [], []
        voice_data, musician_data = [], []
        genre_data = []
        for data in datas:
            work_data.append((data['work_id'],
                              data['detail_link'],
                              data['title'],
                              data['circle'],
                              data['circle_link'],
                              data['category'],
                              data['sale_date'],
                              data['age_zone'],
                              data['file_format'],
                              data['file_size'],
                              data['description'],
                              data['monopoly'],
                              data['price']))
            option_data.append((data['work_id'],
                                data['thumbnail'],
                                data['cien_link'],
                                data['series'],
                                data['chobit_link'],
                                data['sales'],
                                data['favorites'],
                                data['trial_link'],
                                data['trial_size'],
                                data['rating'],
                                ))
            if data['writers'] is not None:
                writer_data.extend([(data['work_id'], writer)
                                    for writer in data['writers']])

            if data['voices'] is not None:
                voice_data.extend([(data['work_id'], voice)
                                   for voice in data['voices']])

            if data['scenarios'] is not None:
                scenario_data.extend([(data['work_id'], scenario)
                                      for scenario in data['scenarios']])

            if data['illustrators'] is not None:
                illustrator_data.extend([(data['work_id'], illustrator)
                                         for illustrator in data['illustrators']])

            if data['musicians'] is not None:
                musician_data.extend([(data['work_id'], musician)
                                      for musician in data['musicians']])

            if data['genres'] is not None:
                genre_data.extend([(data['work_id'], genre)
                                   for genre in data['genres']])

        lists = [
            (
                'insert into work values (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                work_data
            ),
            (
                'insert into option values (?,?,?,?,?,?,?,?,?,?)',
                option_data
            ),
            (
                'insert into writer values (?,?)',
                writer_data
            ),
            (
                'insert into scenario values (?,?)',
                scenario_data
            ),
            (
                'insert into illustrator values (?,?)',
                illustrator_data
            ),
            (
                'insert into voice values (?,?)',
                voice_data
            ),
            (
                'insert into musician values (?,?)',
                musician_data
            ),
            (
                'insert into genre values (?,?)',
                genre_data
            )
        ]
        uniq: Callable[[List[Any]], List[Any]] = lambda lis: list(set(lis))
        for query, lis in lists:
            self.__connect_db(query, uniq(lis))
