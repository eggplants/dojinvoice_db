"""Command line interface for dojinvoice_db."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from .database import DojinvoiceDatabase
from .download import Download
from .parser import DlsiteDict, Parser


def __get_filepaths(dirpath: str) -> list[Path]:
    """Get the file paths in the specified directory.

    Args:
        dirpath (str): Directory path to search for files.

    Returns:
        list[Path]: List of file paths in the specified directory.
    """
    path = Path.cwd() / dirpath
    return sorted(path.glob("*"))


def main() -> None:
    """Main function to run the script."""
    if input("Download pages? >> ") == "y":
        Download("dlsite").get_all_pages()

    db = DojinvoiceDatabase("dojinvoice.db")
    db.create_tables()

    exclude_ids: list[str] = db.get_work_ids()
    if len(exclude_ids) > 0:
        print(len(exclude_ids), "work(s) have already been committed to existing db!")

    for site in ("dlsite",):
        print("site:", site)
        p = Parser(site, exclude_ids)
        targets = __get_filepaths(site)
        print(len(targets), "lists of works is found!")
        for page_idx, path in enumerate(targets):
            print(f"\033[2K\r\033[31mNow: {path}\033[0m")
            d = asyncio.run(p.parse(path, page_idx))
            print(" =>committing to DB...", end="")
            db.push(cast("list[DlsiteDict]", d))

        print("DONE:", site)


if __name__ == "__main__":
    main()
