import random
import base64

from typing import Optional

from nonebot.utils import logger_wrapper

log = logger_wrapper("ClaWeixin Adapter")


def make_headers(token: Optional[str] = None) -> dict[str, str]:
    uin = str(random.randint(0, 0xFFFFFFFF))
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers