from __future__ import annotations

import shutil
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh Intel Mac OS X 10_13_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/67.0.3396.99 Safari/537.36",
}


class Download:
    def __init__(self, site: str) -> None:
        """Init."""
        self.site = site
        self.save_dir = Path.cwd() / self.site

    def get_all_pages(self) -> None:
        """Get pages till a page without an article is shown."""
        if self.site == "dlsite":
            self.get_dlsite_pages()

    def get_dlsite_pages(self) -> None:
        root = (
            "https://www.dlsite.com/maniax/fsr/=/language/jp/"
            "sex_category%5B0%5D/male/work_category%5B0%5D/doujin/"
            "order%5B0%5D/release_d/work_type%5B0%5D/SOU/"
            "work_type_name%5B0%5D/%E3%83%9C%E3%82%A4%E3%82%B9%E3%83%BBASMR/"
            "per_page/100/page/{}"
        )

        shutil.rmtree(self.save_dir, ignore_errors=True)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        pagenation = 0
        while True:
            pagenation += 1
            filename = f"{pagenation:05}.html"
            url = root.format(pagenation)
            print(f"\33[2K\rnow: {filename}", end="", flush=True)  # noqa: T201
            page_source = requests.get(url, headers=UA, timeout=10).text
            if self.__check_work(page_source):
                self.__save_file(page_source, filename)
            else:
                break

    def __check_work(self, page: str) -> bool:
        """Judge if articles exists in a source."""
        bs = BeautifulSoup(page, "lxml")
        return bs is not None and bs.select_one("li[class=search_result_img_box_inner]") is not None

    def __save_file(self, source: str, filename: str) -> None:
        """Save a file."""
        save_path = Path(self.save_dir) / filename
        print(source, file=save_path.open("w"))
