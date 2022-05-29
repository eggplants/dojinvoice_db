from __future__ import annotations

import os
import urllib.parse
from datetime import datetime as dt
from random import uniform
from time import sleep
from typing import TypedDict, cast

from bs4 import BeautifulSoup as BS
from bs4.element import Tag
from humanfriendly import parse_size
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


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
    thumbnail: str | None
    cien_link: str | None
    series: str | None
    writers: list[str] | None
    scenarios: list[str] | None
    illustrators: list[str] | None
    voices: list[str] | None
    musicians: list[str] | None
    chobit_link: str | None
    sales: int | None
    favorites: int | None
    trial_link: str | None
    trial_size: int | None
    rating: float | None
    genres: list[str] | None


class DmmDict(TypedDict):
    work_id: str
    detail_link: str
    title: str
    thumbnail: str
    samples: list[str | None]
    circle: str
    circle_link: str
    sale_date: int
    use_limit: str | None
    voice_num: str
    file_size: str
    series: str | None
    subject: str
    genre: list[str]
    trial_link: str | None
    description: str
    rating: float | None
    sales: int | None
    favorites: int | None
    price: int


UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh Intel Mac OS X 10_13_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/67.0.3396.99 Safari/537.36"
}


class Parser(object):
    def __init__(self, site: str, exclude_ids: list[str] = []) -> None:
        """Init."""
        self.site = site
        self.exclude_ids = exclude_ids
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-browser-side-navigation")
        options.add_argument('--proxy-server="direct://"')
        options.add_argument("--proxy-bypass-list=*")
        options.add_argument("--start-maximized")
        options.add_argument("--user-agent={}".format(UA["User-Agent"]))
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        print("Preparing for headless chrome...", end="", flush=True)
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(60)
        self.driver.get("https://www.dlsite.com/maniax/work/=/product_id/RJ305341.html")
        WebDriverWait(self.driver, 15).until(
            expected_conditions.presence_of_element_located((By.CLASS_NAME, "btn_yes"))
        )
        btn = self.driver.find_element_by_class_name("btn-approval")
        if btn:
            btn.click()

    def parse(self, path: str, page_idx: int = 0) -> list[DlsiteDict] | list[DmmDict]:
        """Extract required information from the page sources and scrape it."""
        self.page_idx = page_idx
        if self.site == "dlsite":
            return self.__parse_dlsite_pages(path)
        # elif self.site == 'dmm':
        #     return self.__parse_dmm_pages(path)
        else:
            raise ParseUnknownSite("Unknown Site: %s" % self.site)

    def __parse_dlsite_pages(self, path: str) -> list[DlsiteDict]:
        res = []
        bs = BS(open(path, "r").read(), "lxml")
        work_links = [
            str(li.get("href"))
            for li in bs.select(
                "li[class=search_result_img_box_inner] a[class=work_thumb_inner]"
            )
            if isinstance(li.get("href"), str)
        ]
        thumb_links = [
            str(li.get("src"))
            for li in bs.select("li[class=search_result_img_box_inner] img[class=lazy]")
            if isinstance(li.get("src"), str)
        ]
        if len(work_links) != len(thumb_links):
            raise ValueError("number of works != number of thumbnails")
        for idx, (work_link, thumb_link) in enumerate(zip(work_links, thumb_links)):
            print(
                "\33[2K\r{}: {}".format(100 * self.page_idx + idx + 1, work_link),
                end="",
            )
            o = urllib.parse.urlparse(work_link)
            work_id = os.path.splitext(os.path.basename(o.path))[0]
            if work_id in self.exclude_ids:
                continue
            data = cast("DlsiteDict", {})

            for _ in range(5):
                try:
                    self.driver.get(work_link)
                    break
                except TimeoutException:
                    pass
            else:
                raise ConnectionError

            bs = BS(self.driver.page_source, "lxml")
            if bs is None:
                continue
            title = bs.select_one("h1[id=work_name]")
            if title is None:
                print("404 skipped:", work_link)
                continue

            data["work_id"] = work_id

            data["detail_link"] = work_link
            data["title"] = title.string if title.string is not None else ""

            data["thumbnail"] = f"https:{thumb_link}"

            circle_elm = bs.select_one("span[class=maker_name] > a")
            data["circle"] = (
                circle_elm.string
                if circle_elm is not None and circle_elm.string
                else ""
            )

            circle_link_elm = bs.select_one("span[class=maker_name] a")
            data["circle_link"] = (
                str(circle_link_elm.get("href", ""))
                if circle_link_elm is not None
                else ""
            )

            cien_elm = bs.select_one("div[class=link_cien] a")
            data["cien_link"] = (
                str(cien_elm.get("href", "")) if cien_elm is not None else None
            )

            info_table = {
                str(tr.th.string): tr.td
                for tr in bs.select("table[id=work_outline] > tbody > tr")
                if isinstance(tr, Tag)
                and isinstance(tr.th, Tag)
                and isinstance(tr.th.string, str)
                and tr.td is not None
            }

            sale_date_elm = (
                info_table["販売日"].select_one("a") if "販売日" in info_table else None
            )
            sale_date = (
                str(sale_date_elm.string)
                if sale_date_elm is not None and sale_date_elm.string is not None
                else ""
            )

            if "時" in sale_date:
                data["sale_date"] = int(
                    dt.strptime(sale_date, "%Y年%m月%d日 %H時").timestamp()
                )
            else:
                data["sale_date"] = int(dt.strptime(sale_date, "%Y年%m月%d日").timestamp())

            category_elm = (
                info_table["作品形式"].select_one("a") if "作品形式" in info_table else None
            )
            data["category"] = (
                category_elm.string
                if category_elm is not None and category_elm.string is not None
                else ""
            )

            series_elm = (
                info_table["シリーズ名"].select_one("a") if "シリーズ名" in info_table else None
            )
            data["series"] = (
                series_elm.string
                if series_elm is not None and series_elm.string is not None
                else ""
            )

            data["writers"] = (
                [
                    writer.string
                    for writer in info_table["作者"].select("a")
                    if writer.string is not None
                ]
                if "作者" in info_table
                else None
            )
            data["scenarios"] = (
                [
                    scenario.string
                    for scenario in info_table["シナリオ"].select("a")
                    if scenario.string is not None
                ]
                if "シナリオ" in info_table
                else None
            )
            data["illustrators"] = (
                [
                    illustrators.string
                    for illustrators in info_table["イラスト"].select("a")
                    if illustrators.string is not None
                ]
                if "イラスト" in info_table
                else None
            )
            data["voices"] = (
                [_.string for _ in info_table["声優"].select("a")]
                if "声優" in info_table
                else None
            )
            data["musicians"] = (
                [_.string for _ in info_table["音楽"].select("a")]
                if "音楽" in info_table
                else None
            )
            data["age_zone"] = ",".join(
                [
                    age_zone.string
                    for age_zone in info_table["年齢指定"].select("span")
                    if age_zone.string is not None
                ]
            )
            data["file_format"] = info_table["ファイル形式"].get_text()
            data["genres"] = (
                [
                    genre.string
                    for genre in info_table["ジャンル"].select("a")
                    if genre.string is not None
                ]
                if "ジャンル" in info_table
                else None
            )
            file_size_elm = info_table["ファイル容量"].select_one("div[class=main_genre]")
            file_size = (
                file_size_elm.string
                if file_size_elm is not None and file_size_elm.string is not None
                else ""
            )
            data["file_size"] = parse_size(file_size.replace("計", "").replace("総", ""))

            trial_elm = bs.select_one("div[class*=trial_download] > ul > li")
            data["trial_link"], data["trial_size"] = None, None
            if trial_elm is not None:
                trial_link_elm = trial_elm.select_one("a[class=btn_trial]")
                data["trial_link"] = (
                    f"https:{trial_link_elm.get('href')}"
                    if trial_link_elm is not None
                    and isinstance(trial_link_elm.get("href"), str)
                    else None
                )
                trial_size_elm = trial_elm.select_one("span")
                data["trial_size"] = (
                    parse_size(trial_size_elm.string.replace("(", "").replace(")", ""))
                    if trial_size_elm is not None and trial_size_elm.string is not None
                    else None
                )

            description_elm = bs.select_one("div[itemprop=description]")
            data["description"] = (
                description_elm.get_text() if description_elm is not None else ""
            )

            data["monopoly"] = bs.select_one("span[title=DLsite専売]") is not None

            rate_elm = bs.select_one("span[class='point average_count']")
            data["rating"] = (
                float(rate_elm.string)
                if rate_elm is not None and rate_elm.string is not None
                else None
            )

            sales_elm = bs.select_one("dd[class=point]")
            data["sales"] = (
                int(sales_elm.string.replace(",", ""))
                if sales_elm is not None and sales_elm.string is not None
                else None
            )

            favorites_elm = bs.select_one("dd[class=position_fix]")
            data["favorites"] = (
                int(favorites_elm.string.replace(",", ""))
                if favorites_elm is not None and favorites_elm.string is not None
                else None
            )

            price_elm = bs.select_one("div[class=work_buy_content]")
            data["price"] = (
                int(price_elm.string.replace(",", "").replace("円", ""))
                if price_elm is not None and price_elm.string is not None
                else 0
            )

            chobit_elm = bs.select_one("div[class='work_parts type_chobit']>iframe")
            data["chobit_link"] = (
                str(chobit_elm.get("src"))
                if chobit_elm is not None and isinstance(chobit_elm.get("src"), str)
                else None
            )

            sleep(uniform(0.1, 1.0))
            res.append(data)

        return res

    # def __parse_dmm_pages(path: str) -> List[DmmDict]:
    #     print(path, end="\r")
    #     bs = BS(open(path, 'r'), 'lxml')
