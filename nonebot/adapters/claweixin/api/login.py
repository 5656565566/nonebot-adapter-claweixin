import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional, Protocol
from urllib.parse import quote

from .common import build_common_headers

DEFAULT_BOT_TYPE = "3"
DEFAULT_LOGIN_TIMEOUT = 480.0
QR_LONG_POLL_TIMEOUT = 35.0
MAX_QR_REFRESH_COUNT = 3
FIXED_LOGIN_API_ROOT = "https://ilinkai.weixin.qq.com"


class LoginError(RuntimeError):
    pass


class LoginHTTPClient(Protocol):
    async def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class LoginResult:
    connected: bool
    already_connected: bool = False
    bot_id: str = ""
    bot_token: str = ""
    api_root: str = ""
    user_id: str = ""
    message: str = ""


MessageHandler = Callable[[str], None | Awaitable[None]]
QRCodeHandler = Callable[[str], None | Awaitable[None]]
VerifyCodeProvider = Callable[[str], str | Awaitable[str]]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _emit(handler: MessageHandler | None, message: str) -> None:
    if handler:
        await _maybe_await(handler(message))


def _is_timeout_error(exception: Exception) -> bool:
    return "Timeout" in exception.__class__.__name__ or isinstance(
        exception, TimeoutError
    )


async def fetch_qrcode(
    client: LoginHTTPClient,
    api_root: str = FIXED_LOGIN_API_ROOT,
    *,
    bot_type: str = DEFAULT_BOT_TYPE,
    local_token_list: Optional[list[str]] = None,
) -> dict[str, Any]:
    return await client.request_json(
        "POST",
        f"{api_root.rstrip('/')}/ilink/bot/get_bot_qrcode?bot_type={bot_type}",
        headers={
            "Content-Type": "application/json",
            **build_common_headers(),
        },
        json={"local_token_list": (local_token_list or [])[-10:]},
    )


async def poll_qr_status(
    client: LoginHTTPClient,
    api_root: str,
    qrcode_id: str,
    *,
    verify_code: str | None = None,
    timeout: float = QR_LONG_POLL_TIMEOUT,
) -> dict[str, Any]:
    endpoint = (
        f"{api_root.rstrip('/')}/ilink/bot/get_qrcode_status"
        f"?qrcode={quote(qrcode_id, safe='')}"
    )
    if verify_code:
        endpoint += f"&verify_code={quote(verify_code, safe='')}"
    try:
        return await client.request_json(
            "GET",
            endpoint,
            headers=build_common_headers(),
            timeout=timeout,
        )
    except Exception as exception:
        if _is_timeout_error(exception):
            return {"status": "wait"}
        raise


async def _refresh_qrcode(
    client: LoginHTTPClient,
    *,
    bot_type: str,
    local_token_list: Optional[list[str]],
    qrcode_handler: QRCodeHandler,
    message_handler: MessageHandler | None,
    refresh_count: int,
) -> tuple[str, str]:
    await _emit(
        message_handler,
        f"二维码已过期，正在刷新...({refresh_count}/{MAX_QR_REFRESH_COUNT})",
    )
    qr_data = await fetch_qrcode(
        client,
        FIXED_LOGIN_API_ROOT,
        bot_type=bot_type,
        local_token_list=local_token_list,
    )
    qrcode_id = str(qr_data.get("qrcode") or "")
    qrcode_url = str(qr_data.get("qrcode_img_content") or "")
    if not qrcode_id or not qrcode_url:
        raise LoginError("刷新登录二维码失败 返回数据缺少 qrcode 或 qrcode_img_content")
    await _maybe_await(qrcode_handler(qrcode_url))
    return qrcode_id, qrcode_url


async def login_flow(
    client: LoginHTTPClient,
    api_root: str,
    *,
    bot_type: str = DEFAULT_BOT_TYPE,
    local_token_list: Optional[list[str]] = None,
    timeout: float = DEFAULT_LOGIN_TIMEOUT,
    qrcode_handler: QRCodeHandler,
    message_handler: MessageHandler | None = None,
    verify_code_provider: VerifyCodeProvider | None = None,
) -> LoginResult:
    await _emit(message_handler, "未配置任何 CLAWEIXIN_TOKEN 开始登录流程")
    qr_data = await fetch_qrcode(
        client,
        FIXED_LOGIN_API_ROOT,
        bot_type=bot_type,
        local_token_list=local_token_list,
    )
    qrcode_id = str(qr_data.get("qrcode") or "")
    qrcode_url = str(qr_data.get("qrcode_img_content") or "")
    if not qrcode_id or not qrcode_url:
        raise LoginError("获取登录二维码失败 返回数据缺少 qrcode 或 qrcode_img_content")

    await _maybe_await(qrcode_handler(qrcode_url))
    await _emit(message_handler, "等待扫码确认登录（限时 8 分钟）...")

    login_api_root = FIXED_LOGIN_API_ROOT
    start_time = time.time()
    pending_verify_code: str | None = None
    scanned_printed = False
    refresh_count = 1

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            return LoginResult(connected=False, message="登录超时，请重试。")

        poll_timeout = min(QR_LONG_POLL_TIMEOUT, timeout - elapsed)
        status_data = await poll_qr_status(
            client,
            login_api_root,
            qrcode_id,
            verify_code=pending_verify_code,
            timeout=poll_timeout,
        )
        status = status_data.get("status")

        if status == "wait":
            await asyncio.sleep(1)
            continue
        if status == "scaned":
            if pending_verify_code:
                pending_verify_code = None
            if not scanned_printed:
                await _emit(message_handler, "二维码已扫码，请在手机上确认登录")
                scanned_printed = True
            await asyncio.sleep(1)
            continue
        if status == "scaned_but_redirect":
            redirect_host = status_data.get("redirect_host")
            if redirect_host:
                login_api_root = f"https://{redirect_host}"
                await _emit(message_handler, f"登录轮询已切换到: {login_api_root}")
            await asyncio.sleep(1)
            continue
        if status == "need_verifycode":
            if verify_code_provider is None:
                raise LoginError("当前登录流程需要手机配对码验证")
            prompt = (
                "你输入的数字不匹配，请重新输入："
                if pending_verify_code
                else "输入手机微信显示的数字，以继续连接："
            )
            pending_verify_code = str(await _maybe_await(verify_code_provider(prompt)))
            continue
        if status == "verify_code_blocked":
            pending_verify_code = None
            if verify_code_provider is None:
                raise LoginError("多次输入错误，请稍后再试")
            refresh_count += 1
            if refresh_count > MAX_QR_REFRESH_COUNT:
                return LoginResult(
                    connected=False,
                    message="多次输入错误，连接流程已停止。请稍后再试。",
                )
            qrcode_id, _ = await _refresh_qrcode(
                client,
                bot_type=bot_type,
                local_token_list=local_token_list,
                qrcode_handler=qrcode_handler,
                message_handler=message_handler,
                refresh_count=refresh_count,
            )
            scanned_printed = False
            continue
        if status == "binded_redirect":
            message = "已连接过此 OpenClaw，无需重复连接。"
            await _emit(message_handler, message)
            return LoginResult(
                connected=False,
                already_connected=True,
                message=message,
            )
        if status == "expired":
            refresh_count += 1
            if refresh_count > MAX_QR_REFRESH_COUNT:
                return LoginResult(
                    connected=False,
                    message="二维码多次失效，连接流程已停止。请稍后再试。",
                )
            qrcode_id, _ = await _refresh_qrcode(
                client,
                bot_type=bot_type,
                local_token_list=local_token_list,
                qrcode_handler=qrcode_handler,
                message_handler=message_handler,
                refresh_count=refresh_count,
            )
            scanned_printed = False
            continue
        if status == "confirmed":
            bot_id = str(status_data.get("ilink_bot_id") or "")
            bot_token = str(status_data.get("bot_token") or "")
            if not bot_token:
                raise LoginError("登录成功但接口未返回 bot_token")
            return LoginResult(
                connected=True,
                bot_id=bot_id,
                bot_token=bot_token,
                api_root=str(status_data.get("baseurl") or api_root),
                user_id=str(status_data.get("ilink_user_id") or ""),
                message="登录成功",
            )

        raise LoginError(f"未知登录状态: {status}")
