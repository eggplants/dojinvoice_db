from selenium.webdriver.common import service as service, utils as utils
from typing import Any

class Service(service.Service):
    service_args: Any
    quiet: Any
    def __init__(self, executable_path, port: int = ..., quiet: bool = ..., service_args: Any | None = ...) -> None: ...
    def command_line_args(self): ...
    @property
    def service_url(self): ...
