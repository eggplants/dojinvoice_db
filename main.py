import os
from glob import glob
from typing import List, TypedDict

import dojinvoice.database
import dojinvoice.download
import dojinvoice.parser
from dojinvoice.parser import DlsiteDict

# from dojinvoice.parser import DmmDict


class DojinDict(TypedDict):
    dlsite: List[DlsiteDict]
    # dmm: List[DmmDict]


def get_filepaths(dirpath: str) -> List[str]:
    """Get the file paths in the specified directory."""
    return sorted(glob(os.path.join('.', dirpath, '*')))


def main() -> None:
    """Main!!!"""
    if input('Download pages? >> ') == 'y':
        dojinvoice.download.Download('dlsite').get_all_pages()
        # dojinvoice.download.Download('dmm').get_all_pages()

    db = dojinvoice.database.DojinvoiceDatabase('dojinvoice.db')
    db.create_tables()

    parsed_data: DojinDict = {
        'dlsite': []
        # 'dmm': []
    }
    for site in parsed_data.keys():
        parser = dojinvoice.parser.Parser(site)
        targets = get_filepaths(site)
        for page_idx, path in enumerate(targets):
            print('\33[2K\r\033[31mNow: {}\033[0m'.format(path))
            parsed_data[site].extend(parser.parse(path, page_idx))
            db.push(parsed_data['dlsite'])
            parsed_data['dlsite'] = []


if __name__ == '__main__':
    main()
