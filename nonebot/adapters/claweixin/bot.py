from typing import Union, Any, TYPE_CHECKING
from typing_extensions import override

from nonebot.message import handle_event
from nonebot.adapters import Bot as BaseBot

from .event import Event, MessageEvent, Reply
from .message import Message, MessageSegment
from .utils import log

if TYPE_CHECKING:
    from .adapter import Adapter


class Bot(BaseBot):
    adapter: "Adapter"  # type: ignore
    token: str

    @override
    def __init__(self, adapter: "Adapter", self_id: str, token: str = "", **kwargs: Any):
        super().__init__(adapter, self_id, **kwargs)
        self.token = token

    def __getattr__(self, item: str) -> Any:
        raise NotImplementedError(f"API {item} is not supported")

    @override
    async def send(  # type: ignore
        self,
        event: Event,
        message: Union[str, Message, MessageSegment],
        **kwargs: Any,
    ) -> Any:
        if not getattr(event, "from_user_id", None):
            raise ValueError("Can only send message to Event with from_user_id")
            
        return await self.call_api(
            "send_message",
            to_user_id=getattr(event, "from_user_id", ""),
            group_id=getattr(event, "group_id", ""),
            context_token=getattr(event, "context_token", ""),
            message=message
        )

    async def handle_event(self, event: Event):
        log("DEBUG", f"Bot {self.self_id} handling event: {event.get_event_name()}")
        if isinstance(event, MessageEvent):
            self._check_reply(event)
            self._check_at_me(event)
            self._check_nickname(event)
        await handle_event(self, event)

    def _check_reply(self, event: MessageEvent):
        if not hasattr(event, "message"):
            return
        msg = event.message
        if not msg:
            return
        
        reply_segment = None
        for i, segment in enumerate(msg):
            if segment.type == "reply":
                reply_segment = msg.pop(i)
                break
                
        if reply_segment:
            event.reply = Reply(ref_msg=reply_segment.data.get("ref_msg", {}))

    def _check_at_me(self, event: MessageEvent): # 个人对话场景 to_me 保持为 True
        event.to_me = True

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
