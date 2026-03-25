import json
from typing import Optional

from nonebot.drivers import Response
from nonebot.exception import AdapterException
from nonebot.exception import ActionFailed as BaseActionFailed
from nonebot.exception import NetworkError as BaseNetworkError
from nonebot.exception import ApiNotAvailable as BaseApiNotAvailable


class ClaWeixinAdapterException(AdapterException):
    def __init__(self):
        super().__init__("claweixin")

class NetworkError(BaseNetworkError, ClaWeixinAdapterException):
    def __init__(self, msg: Optional[str] = None):
        super().__init__()
        self.msg: Optional[str] = msg
        """错误原因"""

    def __repr__(self):
        return f"<NetWorkError message={self.msg}>"

    def __str__(self):
        return self.__repr__()

class ActionFailed(BaseActionFailed, ClaWeixinAdapterException):
    def __init__(self, response: Response):
        self.status_code: int = response.status_code
        self.code: Optional[int] = None
        self.message: Optional[str] = None
        self.data: Optional[dict] = None
        if response.content:
            try:
                data = json.loads(response.content)
                self.code = data.get("code")
                self.message = data.get("message")
                self.data = data.get("data")
            except Exception:
                pass

    def __repr__(self):
        return f"<ActionFailed status_code={self.status_code} code={self.code} message={self.message}>"

    def __str__(self):
        return self.__repr__()

class UnauthorizedException(ActionFailed):
    pass

class RateLimitException(ActionFailed):
    pass

class ApiNotAvailable(BaseApiNotAvailable, ClaWeixinAdapterException):
    pass
