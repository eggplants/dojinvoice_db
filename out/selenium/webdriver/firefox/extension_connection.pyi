from selenium.webdriver.common import utils as utils
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities as DesiredCapabilities
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary as FirefoxBinary
from selenium.webdriver.remote.command import Command as Command
from selenium.webdriver.remote.remote_connection import RemoteConnection as RemoteConnection
from typing import Any

LOGGER: Any
PORT: int
HOST: Any

class ExtensionConnection(RemoteConnection):
    profile: Any
    binary: Any
    def __init__(self, host, firefox_profile, firefox_binary: Any | None = ..., timeout: int = ...) -> None: ...
    def quit(self, sessionId: Any | None = ...) -> None: ...
    def connect(self): ...
    @classmethod
    def connect_and_quit(self) -> None: ...
    @classmethod
    def is_connectable(self) -> None: ...

class ExtensionConnectionError(Exception): ...
