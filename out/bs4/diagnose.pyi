from bs4 import BeautifulSoup as BeautifulSoup
from bs4.builder import builder_registry as builder_registry
from html.parser import HTMLParser

def diagnose(data) -> None: ...
def lxml_trace(data, html: bool = ..., **kwargs) -> None: ...

class AnnouncingParser(HTMLParser):
    def handle_starttag(self, name, attrs) -> None: ...
    def handle_endtag(self, name) -> None: ...
    def handle_data(self, data) -> None: ...
    def handle_charref(self, name) -> None: ...
    def handle_entityref(self, name) -> None: ...
    def handle_comment(self, data) -> None: ...
    def handle_decl(self, data) -> None: ...
    def unknown_decl(self, data) -> None: ...
    def handle_pi(self, data) -> None: ...

def htmlparser_trace(data) -> None: ...
def rword(length: int = ...): ...
def rsentence(length: int = ...): ...
def rdoc(num_elements: int = ...): ...
def benchmark_parsers(num_elements: int = ...) -> None: ...
def profile(num_elements: int = ..., parser: str = ...) -> None: ...