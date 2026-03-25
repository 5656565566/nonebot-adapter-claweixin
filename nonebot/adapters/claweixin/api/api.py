import base64
import json
import random
from typing import Any, Optional

from nonebot.drivers import HTTPClientMixin, Request, Response

from ..exception import ActionFailed, NetworkError

DEFAULT_LONG_POLL_TIMEOUT = 35.0
DEFAULT_API_TIMEOUT = 15.0
DEFAULT_CONFIG_TIMEOUT = 10.0
DEFAULT_CHANNEL_VERSION = "1.0.2"


def build_base_info() -> dict[str, str]:
    return {"channel_version": DEFAULT_CHANNEL_VERSION}


def build_headers(token: Optional[str] = None) -> dict[str, str]:
    uin = str(random.randint(0, 0xFFFFFFFF))
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def request_json(
    driver: HTTPClientMixin,
    request: Request,
    *,
    action_name: str,
    allow_empty: bool = False,
) -> dict[str, Any]:
    try:
        response: Response = await driver.request(request)
    except Exception as exception:
        raise NetworkError(f"{action_name} request failed: {exception}") from exception

    if not (200 <= response.status_code < 300):
        raise ActionFailed(response)

    if not response.content:
        if allow_empty:
            return {}
        raise NetworkError(f"{action_name} response is empty")

    try:
        data = json.loads(response.content)
    except Exception as exception:
        raise NetworkError(f"{action_name} response is invalid json: {exception}") from exception

    return data if isinstance(data, dict) else {"data": data}


async def get_updates(
    driver: HTTPClientMixin,
    *,
    api_root: str,
    token: str,
    get_updates_buf: str = "",
    timeout: float = DEFAULT_LONG_POLL_TIMEOUT,
) -> dict[str, Any]:
    request = Request(
        method="POST",
        url=f"{api_root}/ilink/bot/getupdates",
        headers=build_headers(token),
        json={
            "get_updates_buf": get_updates_buf,
            "base_info": build_base_info(),
        },
        timeout=timeout,
    )
    return await request_json(driver, request, action_name="getupdates")


async def send_message(
    driver: HTTPClientMixin,
    *,
    api_root: str,
    token: str,
    body: dict[str, Any],
    timeout: float = DEFAULT_API_TIMEOUT,
) -> dict[str, Any]:
    request = Request(
        method="POST",
        url=f"{api_root}/ilink/bot/sendmessage",
        headers=build_headers(token),
        json={**body, "base_info": build_base_info()},
        timeout=timeout,
    )
    return await request_json(driver, request, action_name="sendmessage", allow_empty=True)


async def get_upload_url(
    driver: HTTPClientMixin,
    *,
    api_root: str,
    token: str,
    body: dict[str, Any],
    timeout: float = DEFAULT_API_TIMEOUT,
) -> dict[str, Any]:
    request = Request(
        method="POST",
        url=f"{api_root}/ilink/bot/getuploadurl",
        headers=build_headers(token),
        json={**body, "base_info": build_base_info()},
        timeout=timeout,
    )
    return await request_json(driver, request, action_name="getuploadurl")


async def get_config(
    driver: HTTPClientMixin,
    *,
    api_root: str,
    token: str,
    ilink_user_id: str,
    context_token: Optional[str] = None,
    timeout: float = DEFAULT_CONFIG_TIMEOUT,
) -> dict[str, Any]:
    request = Request(
        method="POST",
        url=f"{api_root}/ilink/bot/getconfig",
        headers=build_headers(token),
        json={
            "ilink_user_id": ilink_user_id,
            "context_token": context_token,
            "base_info": build_base_info(),
        },
        timeout=timeout,
    )
    return await request_json(driver, request, action_name="getconfig")


async def send_typing(
    driver: HTTPClientMixin,
    *,
    api_root: str,
    token: str,
    body: dict[str, Any],
    timeout: float = DEFAULT_CONFIG_TIMEOUT,
) -> dict[str, Any]:
    request = Request(
        method="POST",
        url=f"{api_root}/ilink/bot/sendtyping",
        headers=build_headers(token),
        json={**body, "base_info": build_base_info()},
        timeout=timeout,
    )
    return await request_json(driver, request, action_name="sendtyping", allow_empty=True)
