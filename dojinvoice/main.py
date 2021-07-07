#!/usr/bin/env python

import os
from glob import glob
from typing import List, TypedDict

from .database import DojinvoiceDatabase
from .download import Download
from .parser import DlsiteDict, Parser

# from .parser import DmmDict


class DojinDict(TypedDict):
    dlsite: List[DlsiteDict]
    # dmm: List[DmmDict]


def get_filepaths(dirpath: str) -> List[str]:
    """Get the file paths in the specified directory."""
    return sorted(glob(os.path.join('.', dirpath, '*')))


def main() -> None:
    """Main!!!"""
    if input('Download pages? >> ') == 'y':
        Download('dlsite').get_all_pages()
        # download.Download('dmm').get_all_pages()

    db = DojinvoiceDatabase('dojinvoice.db')
    db.create_tables()

    exclude_ids: List[str] = []
    if os.path.exists('dojinvoice.db') and input('Exclude committed work ids from en existed db? >> ') == 'y':
        exclude_ids = db.get_work_ids()
        print(len(exclude_ids), 'ids found!')

    parsed_data: DojinDict = {
        'dlsite': []
        # 'dmm': []
    }
    for site in parsed_data.keys():
        p = Parser(site, exclude_ids)
        targets = get_filepaths(site)
        for page_idx, path in enumerate(targets):
            print('\33[2K\r\033[31mNow: {}\033[0m'.format(path))
            parsed_data[site].extend(p.parse(path, page_idx))  # type: ignore
            db.push(parsed_data['dlsite'])
            parsed_data['dlsite'] = []


if __name__ == '__main__':
    main()
