from selenium.webdriver.common.desired_capabilities import DesiredCapabilities as DesiredCapabilities
from selenium.webdriver.common.options import ArgOptions as ArgOptions

class ElementScrollBehavior:
    TOP: int
    BOTTOM: int

class Options(ArgOptions):
    KEY: str
    SWITCHES: str
    BROWSER_ATTACH_TIMEOUT: str
    ELEMENT_SCROLL_BEHAVIOR: str
    ENSURE_CLEAN_SESSION: str
    FILE_UPLOAD_DIALOG_TIMEOUT: str
    FORCE_CREATE_PROCESS_API: str
    FORCE_SHELL_WINDOWS_API: str
    FULL_PAGE_SCREENSHOT: str
    IGNORE_PROTECTED_MODE_SETTINGS: str
    IGNORE_ZOOM_LEVEL: str
    INITIAL_BROWSER_URL: str
    NATIVE_EVENTS: str
    PERSISTENT_HOVER: str
    REQUIRE_WINDOW_FOCUS: str
    USE_PER_PROCESS_PROXY: str
    VALIDATE_COOKIE_DOCUMENT_TYPE: str
    def __init__(self) -> None: ...
    @property
    def options(self): ...
    @property
    def browser_attach_timeout(self): ...
    @browser_attach_timeout.setter
    def browser_attach_timeout(self, value) -> None: ...
    @property
    def element_scroll_behavior(self): ...
    @element_scroll_behavior.setter
    def element_scroll_behavior(self, value) -> None: ...
    @property
    def ensure_clean_session(self): ...
    @ensure_clean_session.setter
    def ensure_clean_session(self, value) -> None: ...
    @property
    def file_upload_dialog_timeout(self): ...
    @file_upload_dialog_timeout.setter
    def file_upload_dialog_timeout(self, value) -> None: ...
    @property
    def force_create_process_api(self): ...
    @force_create_process_api.setter
    def force_create_process_api(self, value) -> None: ...
    @property
    def force_shell_windows_api(self): ...
    @force_shell_windows_api.setter
    def force_shell_windows_api(self, value) -> None: ...
    @property
    def full_page_screenshot(self): ...
    @full_page_screenshot.setter
    def full_page_screenshot(self, value) -> None: ...
    @property
    def ignore_protected_mode_settings(self): ...
    @ignore_protected_mode_settings.setter
    def ignore_protected_mode_settings(self, value) -> None: ...
    @property
    def ignore_zoom_level(self): ...
    @ignore_zoom_level.setter
    def ignore_zoom_level(self, value) -> None: ...
    @property
    def initial_browser_url(self): ...
    @initial_browser_url.setter
    def initial_browser_url(self, value) -> None: ...
    @property
    def native_events(self): ...
    @native_events.setter
    def native_events(self, value) -> None: ...
    @property
    def persistent_hover(self): ...
    @persistent_hover.setter
    def persistent_hover(self, value) -> None: ...
    @property
    def require_window_focus(self): ...
    @require_window_focus.setter
    def require_window_focus(self, value) -> None: ...
    @property
    def use_per_process_proxy(self): ...
    @use_per_process_proxy.setter
    def use_per_process_proxy(self, value) -> None: ...
    @property
    def validate_cookie_document_type(self): ...
    @validate_cookie_document_type.setter
    def validate_cookie_document_type(self, value) -> None: ...
    @property
    def additional_options(self): ...
    def add_additional_option(self, name, value) -> None: ...
    def to_capabilities(self): ...
    @property
    def default_capabilities(self): ...