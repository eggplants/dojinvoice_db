from .options import Options as Options
from .service import Service as Service
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from typing import Any

class WebDriver(RemoteWebDriver):
    service: Any
    def __init__(self, executable_path: str = ..., port: int = ..., options: Any | None = ..., desired_capabilities: Any | None = ..., service_log_path: Any | None = ..., keep_alive: bool = ...) -> None: ...
    def quit(self) -> None: ...
