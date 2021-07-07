import abc
from selenium.webdriver.common.utils import keys_to_typing as keys_to_typing
from typing import Any

class FileDetector(metaclass=abc.ABCMeta):
    __metaclass__: Any
    @abc.abstractmethod
    def is_local_file(self, *keys): ...

class UselessFileDetector(FileDetector):
    def is_local_file(self, *keys) -> None: ...

class LocalFileDetector(FileDetector):
    def is_local_file(self, *keys): ...
