from __future__ import annotations

import os
import shutil

import requests
from bs4 import BeautifulSoup as BS

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh Intel Mac OS X 10_13_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/67.0.3396.99 Safari/537.36"
}


class Download(object):
    def __init__(self, site: str) -> None:
        """Init."""
        self.site = site
        self.save_dir = os.path.join(".", self.site)

    def get_all_pages(self) -> None:
        """Get pages till a page without an article is shown."""
        if self.site == "dlsite":
            self.get_dlsite_pages()
        # elif self.site == 'dmm':
        #     self.get_dmm_pages()

    def get_dlsite_pages(self) -> None:
        root = (
            "https://www.dlsite.com/maniax/fsr/=/language/jp/"
            "sex_category%5B0%5D/male/work_category%5B0%5D/doujin/"
            "order%5B0%5D/release_d/work_type%5B0%5D/SOU/"
            "work_type_name%5B0%5D/%E3%83%9C%E3%82%A4%E3%82%B9%E3%83%BBASMR/"
            "per_page/100/page/{}"
        )

        shutil.rmtree(self.save_dir, ignore_errors=True)
        os.makedirs(self.save_dir, exist_ok=True)

        pagenation = 0
        while True:
            pagenation += 1
            filename = f"{pagenation:05}.html"
            url = root.format(pagenation)
            print(f"\33[2K\rnow: {filename}", end="", flush=True)
            page_source = requests.get(url, headers=UA).text
            if self.__check_work(page_source):
                self.__save_file(page_source, filename)
            else:
                break

    def __check_work(self, page: str) -> bool:
        """Judge if articles exists in a source."""
        bs = BS(page, "lxml")
        return (
            bs is not None
            and bs.select_one("li[class=search_result_img_box_inner]") is not None
        )

    def __save_file(self, source: str, filename: str) -> None:
        """Save a file."""
        print(source, file=open(os.path.join(self.save_dir, filename), "w"))

    # def get_dmm_pages(self) -> None:
    #     root = 'https://www.dmm.co.jp/dc/doujin/-/list/=/media=voice/page={}'
    #     url_certification = BS(
    #         requests.get(root.format(1), headers=UA).text, 'lxml'
    #     ).find(
    #         'a', class_="ageCheck__link ageCheck__link--r18"
    #     ).get('href')
    #     session = requests.session()
    #     session.get(url_certification)
    #     # Judge if articles exists in a source.
    #     max_page = int(
    #         re.search(
    #             r'(?<=全).*(?=タイトル)',
    #             BS(session.get(root.format(1)).content, "lxml").find(
    #                 'p', class_='pageNation__txt').text
    #         ).group().replace(',', ''))//120+2
    #     # Save a file.
    #     save_file: Callable[[str, str], None] = lambda source, filename:\
    #         print(source,
    #               file=open(os.path.join(self.save_dir, filename), 'w'))

    #     shutil.rmtree(self.save_dir, ignore_errors=True)
    #     os.makedirs(self.save_dir, exist_ok=True)

    #     for pagenation in range(1, max_page):
    #         filename = '{:04}.html'.format(pagenation)
    #         url = root.format(pagenation)
    #         print('\33[2K\r{}'.format(url), end='', flush=True)
    #         source = session.get(url).text
    #         save_file(source, filename)
