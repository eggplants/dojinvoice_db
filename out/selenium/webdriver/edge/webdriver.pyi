from .service import Service as Service
from selenium.webdriver.common import utils as utils
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities as DesiredCapabilities
from selenium.webdriver.remote.remote_connection import RemoteConnection as RemoteConnection
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from typing import Any

DEFAULT_PORT: int
DEFAULT_SERVICE_LOG_PATH: Any

class WebDriver(RemoteWebDriver):
    port: Any
    edge_service: Any
    def __init__(self, executable_path: str = ..., capabilities: Any | None = ..., port=..., verbose: bool = ..., service_log_path: Any | None = ..., log_path=..., service: Any | None = ..., options: Any | None = ..., keep_alive: bool = ...) -> None: ...
    def quit(self) -> None: ...
