from typing import Any, Optional, Dict, TYPE_CHECKING, cast
from typing_extensions import override
import json
import asyncio
import datetime
import traceback
import random

from nonebot import get_plugin_config
from nonebot.drivers import Driver, Request, HTTPClientMixin

from nonebot.adapters import Adapter as BaseAdapter

from .bot import Bot
from .config import Config
from .exception import NetworkError, ActionFailed
from .utils import make_headers, log
from .event import PrivateMessageEvent
from .login import login_flow

if TYPE_CHECKING:
    from .message import Message, MessageSegment


class Adapter(BaseAdapter):

    @override
    def __init__(self, driver: Driver, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.claweixin_config = get_plugin_config(Config)
        self.tasks: list[asyncio.Task] = []
        self.typing_ticket_cache: Dict[str, str] = {}
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
        self.driver.on_startup(self._startup)
        self.driver.on_shutdown(self._shutdown)

    def _get_tokens(self) -> list[str]:
        tokens = getattr(self.claweixin_config, "claweixin_token", [])
        if isinstance(tokens, str):
            return [tokens] if tokens else []
        return [token for token in tokens if token]

    async def _startup(self) -> None:
        log("DEBUG", "Starting ClaWeixin adapter...")
        tokens = self._get_tokens()
        api_root = getattr(self.claweixin_config, "claweixin_api_root", "https://ilinkai.weixin.qq.com")
        qrcode_in_info = getattr(self.claweixin_config, "claweixin_login_qrcode_in_info", False)

        
        login_result = await login_flow(
            cast(HTTPClientMixin, self.driver),
            api_root,
            qrcode_in_info=qrcode_in_info,
        )

        if login_result: # 加一个临时登陆使用
            tokens = [login_result["bot_token"]]
        else:
            log("WARNING", "ClaWeixin login flow finished without token")

        for index, token in enumerate(tokens, start=1):
            bot = Bot(self, f"claweixin_bot_{index}", token=token)
            self.bot_connect(bot)
            log("DEBUG", f"Bot {bot.self_id} connected.")
            self.tasks.append(asyncio.create_task(self._poll_updates(bot, token)))

    async def _shutdown(self) -> None:
        log("DEBUG", "Shutting down ClaWeixin adapter...")
        for task in self.tasks:
            if not task.done():
                task.cancel()
        for bot in list(self.bots.values()):
            self.bot_disconnect(bot)

    async def _poll_updates(self, bot: Bot, token: str) -> None:
        api_root = getattr(self.claweixin_config, "claweixin_api_root", "https://ilinkai.weixin.qq.com")
        get_updates_buf = ""

        log("DEBUG", f"Start long polling for bot {bot.self_id} at {api_root}")
        while True:
            try:
                headers = make_headers(token)
                payload = {
                    "get_updates_buf": get_updates_buf,
                    "base_info": {"channel_version": "1.0.2"},
                }
                request = Request(
                    method="POST",
                    url=f"{api_root}/ilink/bot/getupdates",
                    headers=headers,
                    json=payload,
                    timeout=40.0,
                )
                log("DEBUG", f"Sending getupdates request with buf length: {len(get_updates_buf)}")

                start_time = asyncio.get_event_loop().time()
                response = await self.request(request)

                if response.status_code == 200 and response.content:
                    data = json.loads(response.content)
                    log("DEBUG", f"getupdates response: {str(data)[:200]}")

                    if data.get("errcode", 0) != 0 or data.get("base_resp", {}).get("ret", 0) != 0:
                        log("ERROR", f"WeChat API Error, pausing 5s... Data: {data}")
                        await asyncio.sleep(5)
                        continue

                    get_updates_buf = data.get("get_updates_buf") or get_updates_buf
                    msgs = data.get("msgs") or []
                    for msg in msgs:
                        if msg.get("message_type") != 1:
                            continue

                        try:
                            from_id = msg.get("from_user_id", "")
                            context_token = msg.get("context_token", "")

                            if from_id and context_token:
                                if from_id not in self.typing_ticket_cache:
                                    cfg_req = Request(
                                        method="POST",
                                        url=f"{api_root}/ilink/bot/getconfig",
                                        headers=headers,
                                        json={
                                            "ilink_user_id": from_id,
                                            "context_token": context_token,
                                            "base_info": {"channel_version": "1.0.2"},
                                        },
                                    )
                                    cfg_res = await self.request(cfg_req)
                                    if cfg_res.status_code == 200 and cfg_res.content:
                                        cfg_data = json.loads(cfg_res.content)
                                        self.typing_ticket_cache[from_id] = cfg_data.get("typing_ticket", "")

                                typing_ticket = self.typing_ticket_cache.get(from_id, "")
                                if typing_ticket:
                                    type_req = Request(
                                        method="POST",
                                        url=f"{api_root}/ilink/bot/sendtyping",
                                        headers=headers,
                                        json={"ilink_user_id": from_id, "typing_ticket": typing_ticket, "status": 1},
                                    )
                                    asyncio.create_task(self.request(type_req))

                            event = self._parse_message(msg)
                            if event:
                                log("DEBUG", f"Dispatching event: {event.get_event_name()} (id: {event.message_id})")
                                asyncio.create_task(bot.handle_event(event))
                        except Exception as e:
                            log("ERROR", f"Failed to parse message: {e}\n{traceback.format_exc()}")
                elif response.status_code != 200:
                    log("WARNING", f"getUpdates failed with HTTP status {response.status_code}")
                    await asyncio.sleep(5)

                if asyncio.get_event_loop().time() - start_time < 1.0:
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                log("DEBUG", "Long polling task cancelled.")
                break
            except Exception as e:
                log("ERROR", f"Error in long poll: {e}")
                await asyncio.sleep(5)

    def _parse_message(self, msg: Dict[str, Any]) -> Optional[Any]:
        create_time = datetime.datetime.fromtimestamp(msg.get("create_time_ms", 0) / 1000.0)

        base_kwargs = {
            "time": create_time,
            "message_id": str(msg.get("message_id", "")),
            "seq": msg.get("seq"),
            "from_user_id": msg.get("from_user_id", ""),
            "to_user_id": msg.get("to_user_id", ""),
            "client_id": msg.get("client_id"),
            "create_time_ms": msg.get("create_time_ms"),
            "update_time_ms": msg.get("update_time_ms"),
            "delete_time_ms": msg.get("delete_time_ms"),
            "session_id": msg.get("session_id"),
            "group_id": msg.get("group_id"),
            "message_type": msg.get("message_type"),
            "message_state": msg.get("message_state"),
            "item_list": msg.get("item_list", []),
            "context_token": msg.get("context_token"),
        }

        return PrivateMessageEvent(**base_kwargs)

    @override
    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:  # type: ignore
        api_root = getattr(self.claweixin_config, "claweixin_api_root", "https://ilinkai.weixin.qq.com")
        token = getattr(bot, "token", "")
        headers = make_headers(token)

        log("DEBUG", f"Calling API: {api} with data: {data}")

        if api == "send_message":
            endpoint = "/ilink/bot/sendmessage"
            message = data.get("message")
            if isinstance(message, str):
                message_list = [MessageSegment.text(message)]
            elif hasattr(message, "type"):
                message_list = [message]
            else:
                message_list = message or []

            item_list = []
            for seg in message_list:
                if getattr(seg, "type", None) == "text":
                    item_list.append({
                        "type": 1,
                        "text_item": {"text": getattr(seg, "data", {}).get("text", "")},
                    })
                elif getattr(seg, "type", None) == "image":
                    item_list.append({
                        "type": 2,
                        "image_item": {"url": getattr(seg, "data", {}).get("url", "")},
                    })

            client_id = f"openclaw-weixin-{random.randint(0, 0xFFFFFFFF):08x}"
            to_user_id = data.get("to_user_id")
            payload = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "group_id": data.get("group_id"),
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": data.get("context_token"),
                    "item_list": item_list,
                },
                "base_info": {"channel_version": "1.0.2"},
            }
            request = Request(
                method="POST",
                url=f"{api_root}{endpoint}",
                headers=headers,
                json=payload,
            )
            if not to_user_id:
                log("ERROR", "Missing to_user_id in send_message")
                raise ValueError("to_user_id is required")
        else:
            raise NotImplementedError(f"API {api} is not implemented")

        try:
            response = await self.request(request)
            log("DEBUG", f"API response status: {response.status_code}")

            if api == "send_message" and to_user_id:
                typing_ticket = self.typing_ticket_cache.get(to_user_id, "")
                if typing_ticket:
                    type_req_close = Request(
                        method="POST",
                        url=f"{api_root}/ilink/bot/sendtyping",
                        headers=headers,
                        json={"ilink_user_id": to_user_id, "typing_ticket": typing_ticket, "status": 2},
                    )
                    asyncio.create_task(self.request(type_req_close))

        except Exception as e:
            log("ERROR", f"Network error when calling {api}: {e}")
            raise NetworkError(str(e)) from e

        if 200 <= response.status_code < 300:
            if not response.content:
                return None
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                raise ActionFailed(response)
        raise ActionFailed(response)
