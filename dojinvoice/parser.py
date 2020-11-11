from datetime import datetime as dt
from random import uniform
from time import sleep
from typing import List, Optional, TypedDict, Union, cast

from bs4 import BeautifulSoup as BS  # type: ignore
from humanfriendly import parse_size
from selenium import webdriver  # type: ignore
from selenium.webdriver.chrome.options import Options  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support import expected_conditions  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore


class ParseUnknownSite(Exception):
    pass


class DlsiteDict(TypedDict):
    work_id: str
    detail_link: str
    title: str
    circle: str
    circle_link: str
    sale_date: int
    age_zone: str
    category: str
    file_format: str
    file_size: int
    description: str
    monopoly: bool
    price: int
    thumbnail: Optional[str]
    cien_link: Optional[str]
    series: Optional[str]
    writers: Optional[List[str]]
    scenarios: Optional[List[str]]
    illustrators: Optional[List[str]]
    voices: Optional[List[str]]
    musicians: Optional[List[str]]
    chobit_link: Optional[str]
    sales: Optional[int]
    favorites: Optional[int]
    trial_link: Optional[str]
    trial_size: Optional[int]
    rating: Optional[float]
    genres: Optional[List[str]]


class DmmDict(TypedDict):
    work_id: str
    detail_link: str
    title: str
    thumbnail: str
    samples: List[Optional[str]]
    circle: str
    circle_link: str
    sale_date: int
    use_limit: Optional[str]
    voice_num: str
    file_size: str
    series: Optional[str]
    subject: str
    genre: List[str]
    trial_link: Optional[str]
    description: str
    rating: Optional[float]
    sales: Optional[int]
    favorites: Optional[int]
    price: int


UA = {
    'User-Agent': 'Mozilla/5.0 (Macintosh Intel Mac OS X 10_13_5) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/67.0.3396.99 Safari/537.36'}


class Parser(object):

    def __init__(self, site: str) -> None:
        """Init."""
        self.site = site
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--proxy-server="direct://"')
        options.add_argument('--proxy-bypass-list=*')
        options.add_argument('--start-maximized')
        options.add_argument('--user-agent={}'.format(UA['User-Agent']))
        print('Preparing for headless chrome...', end='', flush=True)
        self.driver = webdriver.Chrome(options=options)
        self.driver.get(
            'https://www.dlsite.com/maniax/work/=/product_id/RJ305341.html')
        WebDriverWait(self.driver, 15).until(
            expected_conditions.presence_of_element_located(
                (By.CLASS_NAME, 'btn_yes')))
        btn = self.driver.find_element_by_class_name('btn-approval')
        if btn:
            btn.click()

    def parse(self, path: str, page_idx: int = 0
              ) -> Union[List[DlsiteDict], List[DmmDict]]:
        """Extract required information from the page sources and scrape it."""
        self.page_idx = page_idx
        if self.site == 'dlsite':
            return self.__parse_dlsite_pages(path)
        # elif self.site == 'dmm':
        #     return self.__parse_dmm_pages(path)
        else:
            raise ParseUnknownSite('Unknown Site: %s' % self.site)

    def __parse_dlsite_pages(self, path: str) -> List[DlsiteDict]:
        res = []
        bs = BS(open(path, 'r'), 'lxml')
        work_links = [_.find('a').get('href')
                      for _ in bs.find_all(
            'li', class_='search_result_img_box_inner')]
        thumb_links = [_.find('img').get('src')
                       for _ in bs.find_all(
            'li', class_='search_result_img_box_inner')]
        for idx, work_link in enumerate(work_links):
            print('\33[2K\r{}: {}'.format(100*self.page_idx+idx+1, work_link), end='')
            data = cast('DlsiteDict', {})
            self.driver.get(work_link)
            bs = BS(self.driver.page_source, 'lxml')
            data['work_id'] = work_link.split("/")[-1][:-5]
            data['detail_link'] = work_link
            data['title'] = bs.h1.a.string
            data['thumbnail'] = ('https:' + thumb_links[idx]
                                 if thumb_links[idx] else None)
            data['circle'] = bs.find(
                'span', class_='maker_name').a.string
            data['circle_link'] = bs.find(
                'span', class_='maker_name').a['href']
            cien = bs.find('div', class_='link_cien')
            data['cien_link'] = (cien.a['href'] if cien else None)
            info_table = {_.th.string: _.td for _ in bs.find(
                'table', id='work_outline').find_all('tr')}

            sale_date = info_table['販売日'].a.string
            if '時' in sale_date:
                data['sale_date'] = int(dt.strptime(
                    info_table['販売日'].a.string, '%Y年%m月%d日 %H時').timestamp())
            else:
                data['sale_date'] = int(dt.strptime(
                    info_table['販売日'].a.string, '%Y年%m月%d日').timestamp())

            data['category'] = info_table['作品形式'].a.string
            data['series'] = (
                info_table['シリーズ名'].a.string
                if 'シリーズ名' in info_table else None)
            data['writers'] = (
                [_.string for _ in info_table['作者'].find_all('a')]
                if '作者' in info_table else None)
            data['scenarios'] = (
                [_.string for _ in info_table['シナリオ'].find_all('a')]
                if 'シナリオ' in info_table else None)
            data['illustrators'] = (
                [_.string for _ in info_table['イラスト'].find_all('a')]
                if 'イラスト' in info_table else None)
            data['voices'] = (
                [_.string for _ in info_table['声優'].find_all('a')]
                if '声優' in info_table else None)
            data['musicians'] = (
                [_.string for _ in info_table['音楽'].find_all('a')]
                if '音楽' in info_table else None)
            data['age_zone'] = info_table['年齢指定'].string
            data['file_format'] = info_table['ファイル形式'].get_text()
            data['genres'] = (
                [_.string for _ in info_table['ジャンル'].find_all('a')]
                if 'ジャンル' in info_table else None)
            file_size = info_table['ファイル容量'].div.string
            data['file_size'] = parse_size(
                file_size.replace('計', '').replace('総', ''))
            trial_elm = bs.find('div', class_='trial_download clearfix')
            data['trial_link'] = (
                'https:' + trial_elm.a['href']
                if trial_elm is not None and trial_elm.find('a') else None)
            data['trial_size'] = (
                parse_size(trial_elm.span.string[1:-1])
                if trial_elm is not None and trial_elm.find('a') else None)
            data['description'] = bs.find(
                'div', itemprop='description').get_text()
            data['monopoly'] = not not bs.find('span', title='DLsite専売')
            rate = bs.find('span', class_='point average_count')
            data['rating'] = (float(rate.get_text()) if rate else None)
            sales = bs.find('dd', class_='point')
            data['sales'] = (
                int(sales.get_text().replace(',', '')) if sales else None)
            favorites = bs.find('dd', class_='position_fix')
            data['favorites'] = (
                int(favorites.get_text().replace(',', ''))
                if favorites else None)
            data['price'] = int(bs.find(
                'div', class_='work_buy_content'
            ).get_text().replace(',', '').replace('円', ''))
            chobit = bs.find('div', class_='work_parts type_chobit')
            data['chobit_link'] = (
                chobit.iframe['src'] if chobit else None)
            # print(data)
            sleep(uniform(0.1, 1.0))
            res.append(data)
        return res

    # def __parse_dmm_pages(path: str) -> List[DmmDict]:
    #     print(path, end="\r")
    #     bs = BS(open(path, 'r'), 'lxml')
