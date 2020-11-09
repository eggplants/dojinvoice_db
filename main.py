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

    parsed_data: DojinDict = {
        'dlsite': []
        # 'dmm': []
    }
    for site in parsed_data.keys():
        parser = dojinvoice.parser.Parser(site)
        for page_idx, path in enumerate(get_filepaths(site)[:1]):
            parsed_data[site].extend(parser.parse(path, page_idx))

    db = dojinvoice.database.DojinvoiceDatabase('dojinvoice.db')
    if not os.path.exists('dojinvoice.db'):
        db.create_tables()

    db.push(parsed_data['dlsite'])


if __name__ == '__main__':
    main()
