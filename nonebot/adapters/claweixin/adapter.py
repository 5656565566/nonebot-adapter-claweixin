import json
import asyncio
import datetime
import traceback

from typing import Any, Optional, Dict, TYPE_CHECKING, cast
from typing_extensions import override

from nonebot import get_plugin_config
from nonebot.drivers import Driver, Request, HTTPClientMixin

from nonebot.adapters import Adapter as BaseAdapter

from .api.api import get_config, get_updates, send_typing
from .api.media import download_media_from_message
from .api.send import send_segments
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
        return [token for token in self.claweixin_config.claweixin_token if token]

    async def _startup(self) -> None:
        log("DEBUG", "Starting ClaWeixin adapter...")
        tokens = self._get_tokens()
        api_root = self.claweixin_config.claweixin_api_root
        qrcode_in_info = self.claweixin_config.claweixin_login_qrcode_in_info

        if qrcode_in_info:
            login_result = await login_flow(
                cast(HTTPClientMixin, self.driver),
                api_root,
                qrcode_in_info=qrcode_in_info,
            )

            if login_result: # 临时登陆使用
                tokens.append(login_result["bot_token"])
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
        api_root = self.claweixin_config.claweixin_api_root
        get_updates_buf = ""

        log("DEBUG", f"Start long polling for bot {bot.self_id} at {api_root}")
        while True:
            try:
                headers = make_headers(token)
                log("DEBUG", f"Sending getupdates request with buf length: {len(get_updates_buf)}")

                start_time = asyncio.get_running_loop().time()
                data = await get_updates(
                    cast(HTTPClientMixin, self.driver),
                    api_root=api_root,
                    token=token,
                    get_updates_buf=get_updates_buf,
                    timeout=40.0,
                )
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
                                cfg_data = await get_config(
                                    cast(HTTPClientMixin, self.driver),
                                    api_root=api_root,
                                    token=token,
                                    ilink_user_id=from_id,
                                    context_token=context_token,
                                )
                                self.typing_ticket_cache[from_id] = str(cfg_data.get("typing_ticket", "") or "")

                            typing_ticket = self.typing_ticket_cache.get(from_id, "")
                            if typing_ticket:
                                asyncio.create_task(
                                    send_typing(
                                        cast(HTTPClientMixin, self.driver),
                                        api_root=api_root,
                                        token=token,
                                        body={"ilink_user_id": from_id, "typing_ticket": typing_ticket, "status": 1},
                                    )
                                )

                        event = await self._parse_message(msg)
                        if event:
                            log("DEBUG", f"Dispatching event: {event.get_event_name()} (id: {event.message_id})")
                            asyncio.create_task(bot.handle_event(event))
                    except Exception as e:
                        log("ERROR", f"Failed to parse message: {e}\n{traceback.format_exc()}")

                if asyncio.get_running_loop().time() - start_time < 1.0:
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                log("DEBUG", "Long polling task cancelled.")
                break
            except Exception as e:
                log("ERROR", f"Error in long poll: {e}")
                await asyncio.sleep(5)

    async def _parse_message(self, msg: Dict[str, Any]) -> Optional[Any]:
        create_time = datetime.datetime.fromtimestamp(msg.get("create_time_ms", 0) / 1000.0)
        item_list = msg.get("item_list", [])
        media = await download_media_from_message(
            cast(HTTPClientMixin, self.driver),
            item_list=item_list,
            cdn_base_url=self.claweixin_config.claweixin_cdn_root,
        )

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
            "item_list": item_list,
            "context_token": msg.get("context_token"),
            "media_data" : media.media_data,
            "media_type" : media.media_type,
            "file_name": media.file_name,
        }

        return PrivateMessageEvent(**base_kwargs)

    @override
    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:  # type: ignore
        api_root = self.claweixin_config.claweixin_api_root
        token = bot.token

        log("DEBUG", f"Calling API: {api} with data: {data}")

        if api != "send_message":
            raise NotImplementedError(f"API {api} is not implemented")

        message = data.get("message")
        if isinstance(message, str):
            message_list = [MessageSegment.text(message)]
        elif hasattr(message, "type"):
            message_list = [message]
        else:
            message_list = message or []

        to_user_id = data.get("to_user_id")
        if not to_user_id:
            log("ERROR", "Missing to_user_id in send_message")
            raise ValueError("to_user_id is required")

        try:
            result = await send_segments(
                cast(HTTPClientMixin, self.driver),
                api_root=api_root,
                token=token,
                cdn_base_url=self.claweixin_config.claweixin_cdn_root,
                to_user_id=to_user_id,
                context_token=data.get("context_token"),
                segments=message_list,
            )

            typing_ticket = self.typing_ticket_cache.get(to_user_id, "")
            if typing_ticket:
                asyncio.create_task(
                    send_typing(
                        cast(HTTPClientMixin, self.driver),
                        api_root=api_root,
                        token=token,
                        body={"ilink_user_id": to_user_id, "typing_ticket": typing_ticket, "status": 2},
                    )
                )
            return {"message_id": result}
        except Exception as e:
            log("ERROR", f"Network error when calling {api}: {e}")
            raise NetworkError(str(e)) from e
