import argparse
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import qrcode  # type: ignore
except ImportError:
    qrcode = None


def _load_login_api() -> tuple[type[RuntimeError], type[Any], Any]:
    try:
        module = importlib.import_module("nonebot.adapters.claweixin.api.login")
        return module.LoginError, module.LoginResult, module.login_flow
    except ModuleNotFoundError:
        project_root = Path(__file__).resolve().parents[1]
        filtered_path: list[str] = []
        for item in sys.path:
            candidate = Path(item or ".").resolve() / "nonebot/adapters/claweixin"
            if candidate.exists() and not (candidate / "api/login.py").exists():
                continue
            filtered_path.append(item)
        sys.path[:] = filtered_path
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        import nonebot
        import nonebot.adapters

        local_nonebot = str(project_root / "nonebot")
        local_adapters = str(project_root / "nonebot/adapters")
        if local_nonebot not in nonebot.__path__:
            nonebot.__path__.insert(0, local_nonebot)
        if local_adapters not in nonebot.adapters.__path__:
            nonebot.adapters.__path__.insert(0, local_adapters)
        for name in [
            "nonebot.adapters.claweixin.api",
            "nonebot.adapters.claweixin",
        ]:
            sys.modules.pop(name, None)
        module = importlib.import_module("nonebot.adapters.claweixin.api.login")
        return module.LoginError, module.LoginResult, module.login_flow


LoginError, LoginResult, api_login_flow = _load_login_api()


class HttpxLoginHTTPClient:
    def __init__(self) -> None:
        try:
            import httpx # type: ignore
        except ImportError as exception:
            raise LoginError(
                "缺少 httpx 请安装 pip install nonebot-adapter-claweixin[login]"
            ) from exception
        self.httpx = httpx

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        async with self.httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=timeout,
            )
        if not (200 <= response.status_code < 300):
            raise LoginError(f"登录请求失败 HTTP 状态码: {response.status_code}")
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exception:
            raise LoginError("登录接口返回了无效 JSON 数据") from exception
        return data if isinstance(data, dict) else {"data": data}


def _load_local_token_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    stripped = raw.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, str):
        return [parsed] if parsed.strip() else []
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [
        token.strip()
        for token in stripped.replace("\r", "\n").replace(",", "\n").split("\n")
        if token.strip()
    ]


def display_qr(qrcode_url: str) -> None:
    print(f"\n请使用微信扫描以下二维码或打开链接:\n{qrcode_url}\n")
    if not qrcode:
        print("安装 qrcode 库可在终端直接显示二维码 如: pip install qrcode")
        return

    qr = qrcode.QRCode(border=1)
    qr.add_data(qrcode_url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


async def read_verify_code(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip()


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ClaWeixin 登录工具")
    parser.add_argument(
        "--api-root",
        default="https://ilinkai.weixin.qq.com",
        help="Weixin API 根地址",
    )
    parser.add_argument(
        "--local-token",
        action="append",
        default=[],
        help="本地已有 bot_token 可重复传入 用于识别已绑定账号",
    )
    return parser


async def _run_cli_login(api_root: str, local_token_list: list[str]) -> int:
    tokens = local_token_list or _load_local_token_list(os.getenv("CLAWEIXIN_TOKEN"))
    try:
        result = await api_login_flow(
            HttpxLoginHTTPClient(),
            api_root,
            local_token_list=tokens,
            qrcode_handler=display_qr,
            message_handler=print,
            verify_code_provider=read_verify_code,
        )
    except LoginError as exception:
        print(f"claweixin-login 失败: {exception}", file=sys.stderr)
        return 1
    except Exception as exception:
        print(f"claweixin-login 失败: {exception}", file=sys.stderr)
        return 1

    if result.already_connected:
        return 0
    if not result.connected:
        print(result.message or "claweixin-login 未完成登录", file=sys.stderr)
        return 1

    print("\n登录成功 如需持久化使用请将以下配置写入环境变量")
    print(f'CLAWEIXIN_TOKEN=["{result.bot_token}"]')
    if result.api_root and result.api_root != api_root:
        print(f'CLAWEIXIN_API_ROOT="{result.api_root}"')
    if result.bot_id:
        print(f"ilink_bot_id={result.bot_id}")
    if result.user_id:
        print(f"ilink_user_id={result.user_id}")
    return 0


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run_cli_login(args.api_root, args.local_token)))


if __name__ == "__main__":
    main()
