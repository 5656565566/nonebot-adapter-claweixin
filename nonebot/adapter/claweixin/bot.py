from typing import Union, Any, TYPE_CHECKING
from typing_extensions import override

from nonebot.message import handle_event
from nonebot.adapters import Bot as BaseBot

from .event import Event, MessageEvent
from .message import Message, MessageSegment

if TYPE_CHECKING:
    from .adapter import Adapter


class Bot(BaseBot):
    adapter: "Adapter"

    @override
    def __init__(self, adapter: "Adapter", self_id: str, **kwargs):
        super().__init__(adapter, self_id, **kwargs)

    def __getattr__(self, item: str) -> Any:
        raise NotImplementedError(f"API {item} is not supported")

    @override
    async def send(
        self,
        event: Event,
        message: Union[str, Message, MessageSegment],
        **kwargs,
    ) -> Any:
        ...

    async def handle_event(self, event: Event):
        if isinstance(event, MessageEvent):
            self._check_reply(event)
            self._check_at_me(event)
            self._check_nickname(event)
        await handle_event(self, event)

    def _check_reply(self, event: MessageEvent):
        # 提取回复并赋值，如果回复了 bot 自己，设置 to_me 为 True
        pass

    def _check_at_me(self, event: MessageEvent):
        if not hasattr(event, "message"):
            return
        msg = event.message
        if not msg:
            return
            
        # 检查首部 at
        if msg[0].type == "at" and msg[0].data.get("qq") == self.self_id:
            event.to_me = True
            msg.pop(0)
            if msg and msg[0].type == "text":
                msg[0].data["text"] = msg[0].data["text"].lstrip()
                if not msg[0].data["text"]:
                    msg.pop(0)
        
        # 检查尾部 at
        if msg and msg[-1].type == "at" and msg[-1].data.get("qq") == self.self_id:
            event.to_me = True
            msg.pop(-1)
            if msg and msg[-1].type == "text":
                msg[-1].data["text"] = msg[-1].data["text"].rstrip()
                if not msg[-1].data["text"]:
                    msg.pop(-1)

    def _check_nickname(self, event: MessageEvent):
        if not hasattr(event, "message"):
            return
        msg = event.message
        if not msg:
            return
        
        nicknames = set(self.config.nickname)
        if not nicknames:
            return
            
        if msg[0].type == "text":
            text = msg[0].data["text"]
            for nickname in nicknames:
                if text.startswith(nickname):
                    event.to_me = True
                    msg[0].data["text"] = text[len(nickname):].lstrip()
                    if not msg[0].data["text"]:
                        msg.pop(0)
                    break
