import os
import re
import shutil
from typing import Callable

import requests
from bs4 import BeautifulSoup as BS  # type: ignore

UA = {
    'User-Agent': 'Mozilla/5.0 (Macintosh Intel Mac OS X 10_13_5) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/67.0.3396.99 Safari/537.36'}


class Download(object):
    def __init__(self, site: str) -> None:
        """Init."""
        self.site = site
        self.save_dir = os.path.join('.', self.site)

    def get_all_pages(self) -> None:
        """Get pages till a page without an article is shown."""
        if self.site == 'dlsite':
            self.get_dlsite_pages()
        elif self.site == 'dmm':
            self.get_dmm_pages()

    def get_dlsite_pages(self):
        root = 'https://www.dlsite.com/maniax/works/voice?page={}'
        # Judge if articles exists in a source.
        chk_work_exist: Callable[[str], bool] = lambda page:\
            not not BS(page, "lxml").find(
            'li', class_='search_result_img_box_inner')
        # Save a file.
        save_file: Callable[[str, str], None] = lambda source, filename:\
            print(source,
                  file=open(os.path.join(self.save_dir, filename), 'w'))

        shutil.rmtree(self.save_dir, ignore_errors=True)
        os.makedirs(self.save_dir, exist_ok=True)

        for pagenation in range(1, 1000):
            filename = '{:04}.html'.format(pagenation)
            url = root.format(pagenation)
            print('\33[2K\r{}'.format(url), end='', flush=True)
            fid = requests.get(url, headers=UA).text
            if chk_work_exist(fid):
                save_file(fid, filename)
            else:
                break

    def get_dmm_pages(self):
        root = 'https://www.dmm.co.jp/dc/doujin/-/list/=/media=voice/page={}'
        url_certification = BS(
            requests.get(root.format(1), headers=UA).text, 'lxml'
        ).find(
            'a', class_="ageCheck__link ageCheck__link--r18"
        ).get('href')
        session = requests.session()
        session.get(url_certification)
        # Judge if articles exists in a source.
        max_page = int(
            re.search(
                r'(?<=全).*(?=タイトル)',
                BS(session.get(root.format(1)).content, "lxml").find(
                    'p', class_='pageNation__txt').text
            ).group().replace(',', ''))//120+2
        # Save a file.
        save_file: Callable[[str, str], None] = lambda source, filename:\
            print(source,
                  file=open(os.path.join(self.save_dir, filename), 'w'))

        shutil.rmtree(self.save_dir, ignore_errors=True)
        os.makedirs(self.save_dir, exist_ok=True)

        for pagenation in range(1, max_page):
            filename = '{:04}.html'.format(pagenation)
            url = root.format(pagenation)
            print('\33[2K\r{}'.format(url), end='', flush=True)
            source = session.get(url).text
            save_file(source, filename)
