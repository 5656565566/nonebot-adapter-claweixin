from typing import Any, Optional
from typing_extensions import override
import json

from nonebot import get_plugin_config
from nonebot.drivers import (
    Driver,
    Request,
    HTTPClientMixin,
    WebSocketClientMixin,
)

from nonebot.adapters import Adapter as BaseAdapter

from .bot import Bot
from .config import Config
from .exception import NetworkError, ActionFailed
from .utils import log


class Adapter(BaseAdapter):

    @override
    def __init__(self, driver: Driver, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.claweixin_config = get_plugin_config(Config)
        self.setup()

    @classmethod
    @override
    def get_name(cls) -> str:
        return "ClaWeixin"
        
    def setup(self) -> None:
        if not isinstance(self.driver, HTTPClientMixin):
            raise RuntimeError(
                f"Current driver {self.driver.type} does not support http client requests! "
                f"ClaWeixin Adapter needs a HTTPClient Driver to work."
            )
        if not isinstance(self.driver, WebSocketClientMixin):
            raise RuntimeError(
                f"Current driver {self.driver.type} does not support websocket client! "
                f"ClaWeixin Adapter needs a WebSocketClient Driver to work."
            )
        # self.driver.on_startup(self.startup)
        # self.driver.on_shutdown(self.shutdown)

    @override
    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        # Example implementation
        request = Request(
            method="POST",
            url=f"https://api.example.com/{api}",
            json=data,
        )
        try:
            response = await self.request(request)
        except Exception as e:
            raise NetworkError(str(e)) from e

        if 200 <= response.status_code < 300:
            if not response.content:
                return None
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                raise ActionFailed(response)
        raise ActionFailed(response)
