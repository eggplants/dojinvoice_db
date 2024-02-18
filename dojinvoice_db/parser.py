from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from random import uniform
from typing import TypedDict, cast
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from humanfriendly import parse_size
from install_playwright import install
from playwright.sync_api import sync_playwright


class UnknownSiteError(Exception):
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
    "Chrome/67.0.3396.99 Safari/537.36",
}


class Parser:
    def __init__(self, site: str, exclude_ids: list[str] | None = None) -> None:
        """Init."""
        self.site = site
        self.exclude_ids = exclude_ids

        print("Preparing for headless chrome...", end="", flush=True)  # noqa: T201

        self.__setup()

    def __setup(self) -> None:
        self.playwright = sync_playwright().start()
        install(self.playwright.chromium)
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-browser-side-navigation",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu",
                "--disable-infobars",
                "--no-sandbox",
                "--no-zygote",
                "--remote-debugging-port=9222",
                "--single-process",
                "--window-size=485,275",
            ],
        )
        self.context = self.browser.new_context(user_agent=UA["User-Agent"])
        self.page = self.context.new_page()
        self.page.set_default_timeout(100000)  # 100s
        self.page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in ("image", "media", "font", "other")
                else route.continue_()
            ),
        )

        self.page.goto("https://www.dlsite.com")
        self.context.add_cookies(
            [
                {
                    "url": "https://www.dlsite.com",
                    "name": "locale",
                    "value": "ja-jp",
                },
                {
                    "url": "https://www.dlsite.com",
                    "name": "adultchecked",
                    "value": "1",
                },
            ],
        )

    def __close(self) -> None:
        self.page.close()
        self.context.close()
        self.browser.close()
        self.playwright.stop()

    def parse(self, path: Path, page_idx: int = 0) -> list[DlsiteDict] | list[DmmDict]:
        """Extract required information from the page sources and scrape it."""
        self.page_idx = page_idx
        if self.site == "dlsite":
            return self.__parse_dlsite_pages(path)
        msg = f"Unknown Site: {self.site}"
        raise UnknownSiteError(msg)

    def __parse_dlsite_pages(self, path: Path) -> list[DlsiteDict]:  # noqa: PLR0915
        res: list[DlsiteDict] = []
        bs = BeautifulSoup(path.open().read(), "lxml")
        work_links = [
            str(a.get("href")) for a in bs.select("a[class=work_thumb_inner]") if isinstance(a.get("href"), str)
        ]
        thumb_links = [
            str(img.get("src") or img.get("data-src"))
            for img in bs.select("img[class=lazy]")
            if isinstance(img.get("src"), str) or isinstance(img.get("data-src"), str)
        ]
        if len(work_links) != len(thumb_links):
            msg = f"number of works != number of thumbnails: ({len(work_links)} != {len(thumb_links)})"
            raise ValueError(msg)
        for idx, (work_link, thumb_link) in enumerate(zip(work_links, thumb_links)):
            print(  # noqa: T201
                f"\33[2K\r{100 * self.page_idx + idx + 1}: {work_link}",
                end="",
            )
            o = urlparse(work_link)
            work_id = Path(o.path).stem
            if self.exclude_ids and work_id in self.exclude_ids:
                continue

            self.page.goto(work_link)
            self.page.locator("div.work_right_info").wait_for()

            title_texts = self.page.locator("h1#work_name").all_text_contents()
            if len(title_texts) != 1:
                print("404 skipped:", work_link)  # noqa: T201
                continue

            data = cast("DlsiteDict", {})
            data["work_id"] = work_id
            data["detail_link"] = work_link
            data["title"] = title_texts[0].strip()

            data["thumbnail"] = urlparse(thumb_link)._replace(scheme="https").geturl()

            data["circle"] = self.page.locator("span[class=maker_name]").all_text_contents()[0].strip()

            circle_link_loc = self.page.locator("span[class=maker_name] a")
            data["circle_link"] = (
                (circle_link_loc.get_attribute("href") or "").strip() if circle_link_loc.count() == 1 else ""
            )

            cien_link_loc = self.page.locator("div[class=link_cien] a")
            data["cien_link"] = (
                (cien_link_loc.get_attribute("href") or "").strip() if cien_link_loc.count() == 1 else None
            )

            info_table = {
                tr.locator("th").all_text_contents()[0]: tr.locator("td")
                for tr in self.page.locator("table[id=work_outline] > tbody > tr").all()
                if tr.locator("td").count() > 0
            }

            sale_date_text = info_table["販売日"].all_text_contents()[0] if "販売日" in info_table else ""
            if "時" in sale_date_text:
                data["sale_date"] = int(
                    datetime.strptime(sale_date_text, "%Y年%m月%d日 %H時").astimezone(timezone.utc).timestamp(),
                )
            else:
                data["sale_date"] = int(
                    datetime.strptime(sale_date_text, "%Y年%m月%d日").astimezone(timezone.utc).timestamp(),
                )

            data["category"] = info_table["作品形式"].all_text_contents()[0].strip() if "作品形式" in info_table else ""

            data["series"] = (
                info_table["シリーズ名"].all_text_contents()[0].strip() if "シリーズ名" in info_table else None
            )

            data["writers"] = (
                [writer.all_text_contents()[0].strip() for writer in info_table["作者"].locator("a").all()]
                if "作者" in info_table
                else None
            )

            data["scenarios"] = (
                [scenario.all_text_contents()[0].strip() for scenario in info_table["シナリオ"].locator("a").all()]
                if "シナリオ" in info_table
                else None
            )

            data["illustrators"] = (
                [
                    illustrator.all_text_contents()[0].strip()
                    for illustrator in info_table["イラスト"].locator("a").all()
                ]
                if "イラスト" in info_table
                else None
            )

            data["voices"] = (
                [voice.all_text_contents()[0].strip() for voice in info_table["声優"].locator("a").all()]
                if "声優" in info_table
                else None
            )

            data["musicians"] = (
                [musician.all_text_contents()[0].strip() for musician in info_table["音楽"].locator("a").all()]
                if "音楽" in info_table
                else None
            )

            data["age_zone"] = ",".join(
                [age_zone.all_text_contents()[0].strip() for age_zone in info_table["年齢指定"].locator("span").all()],
            )
            data["file_format"] = info_table["ファイル形式"].all_text_contents()[0].strip()

            data["genres"] = (
                [genre.all_text_contents()[0].strip() for genre in info_table["ジャンル"].locator("a").all()]
                if "ジャンル" in info_table
                else None
            )

            file_size_text = info_table["ファイル容量"].locator("div[class=main_genre]").all_text_contents()[0]
            data["file_size"] = parse_size(file_size_text.replace("計", "").replace("総", "").strip())

            trial_loc = self.page.locator("div[class*=trial_download] > ul > li")

            trial_link_loc = trial_loc.locator("a[class=btn_trial]")
            data["trial_link"] = (
                urlparse(str(trial_link_loc.get_attribute("href") or ""))._replace(scheme="https").geturl()
                if trial_link_loc.count() == 1
                else None
            )

            trial_size_texts = trial_loc.locator("span").all_text_contents()
            data["trial_size"] = (
                parse_size(trial_size_texts[0].replace("(", "").replace(")", ""))
                if len(trial_size_texts) == 1
                else None
            )

            description_texts = self.page.locator("div[itemprop=description]").all_text_contents()
            data["description"] = "".join(description_texts)

            data["monopoly"] = self.page.locator("span[title=DLsite専売]").count() == 1

            rating_texts = self.page.locator("span[class='point average_count']").all_text_contents()
            data["rating"] = float(rating_texts[0].strip()) if len(rating_texts) == 1 else None
            sales_texts = self.page.locator("dd[class=point]").all_text_contents()
            data["sales"] = int(sales_texts[0].replace(",", "").strip()) if len(sales_texts) == 1 else None

            favorites_texts = self.page.locator("dd[class=position_fix]").all_text_contents()
            data["favorites"] = int(favorites_texts[0].replace(",", "").strip()) if len(favorites_texts) == 1 else None

            price_texts = self.page.locator("span[class=price]").all_text_contents()
            data["price"] = (
                int(price_texts[0].replace(",", "").replace("円", "").strip()) if len(price_texts) == 1 else 0
            )

            if data["price"] == 0:
                price_texts = self.page.locator("div[class=work_buy_content]").all_text_contents()
                data["price"] = (
                    int(price_texts[0].replace(",", "").replace("円", "").strip()) if len(price_texts) == 1 else 0
                )

            chobit_link_loc = self.page.locator("div[class='work_parts type_chobit'] > iframe")
            data["chobit_link"] = chobit_link_loc.get_attribute("src") if chobit_link_loc.count() == 1 else None

            # wait some to avoid page crash
            self.page.wait_for_timeout(uniform(100, 1000))  # noqa: S311

            # debug
            # breakpoint()  # noqa: ERA001

            res.append(data)

        return res
