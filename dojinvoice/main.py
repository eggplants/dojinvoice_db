from __future__ import annotations

import os
from glob import glob
from typing import List, cast

from .database import DojinvoiceDatabase
from .download import Download
from .parser import DlsiteDict, Parser

# from .parser import DmmDict


def get_filepaths(dirpath: str) -> list[str]:
    """Get the file paths in the specified directory."""
    return sorted(glob(os.path.join(".", dirpath, "*")))


def main() -> None:
    """Main!!!"""
    if input("Download pages? >> ") == "y":
        Download("dlsite").get_all_pages()
        # download.Download('dmm').get_all_pages()

    db = DojinvoiceDatabase("dojinvoice.db")
    db.create_tables()

    exclude_ids: list[str] = db.get_work_ids()
    if len(exclude_ids) > 0:
        print(len(exclude_ids), "ids was committed to existed db!")

    for site in ("dlsite",):
        print("site:", site)
        p = Parser(site, exclude_ids)
        targets = get_filepaths(site)
        print(len(targets), "lists of works is found!")
        for page_idx, path in enumerate(targets):
            print("\33[2K\r\033[31mNow: {}\033[0m".format(path))
            d = p.parse(path, page_idx)
            print(" =>committing to DB...", end="")
            db.push(cast(List[DlsiteDict], d))

        print("DONE:", site)


if __name__ == "__main__":
    main()
