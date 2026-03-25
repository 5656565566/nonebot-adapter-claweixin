import datetime
from copy import deepcopy
from typing import Any, Optional, TYPE_CHECKING, List, Dict
from typing_extensions import override

from pydantic import Field
from nonebot.adapters import Event as BaseEvent
from nonebot.compat import model_dump

from .message import Message


class Event(BaseEvent):
    time: datetime.datetime

    @override
    def get_type(self) -> str:
        return ""

    @override
    def get_event_name(self) -> str:
        return self.__class__.__name__

    @override
    def get_event_description(self) -> str:
        return str(model_dump(self))

    @override
    def get_message(self) -> Message:
        raise ValueError("Event has no message!")

    @override
    def get_plaintext(self) -> str:
        raise ValueError("Event has no plaintext!")

    @override
    def get_user_id(self) -> str:
        raise ValueError("Event has no user_id!")

    @override
    def get_session_id(self) -> str:
        raise ValueError("Event has no session_id!")

    @override
    def is_tome(self) -> bool:
        return False


class MessageEvent(Event):
    to_me: bool = True
    reply: Optional[Any] = None
    message_id: str
    
    # 微信原始数据字段
    seq: Optional[int] = None
    from_user_id: str
    to_user_id: str
    client_id: Optional[str] = None
    create_time_ms: Optional[int] = None
    update_time_ms: Optional[int] = None
    delete_time_ms: Optional[int] = None
    session_id: Optional[str] = None
    group_id: Optional[str] = None
    message_type: Optional[int] = None
    message_state: Optional[int] = None
    item_list: List[Dict[str, Any]] = Field(default_factory=list)
    context_token: Optional[str] = None
    
    if TYPE_CHECKING:
        message: Message
        original_message: Message
        
    @override
    def get_type(self) -> str:
        return "message"

    @override
    def get_message(self) -> Message:
        if not hasattr(self, "message"):
            msg = Message.from_message_items(self.item_list)
            setattr(self, "message", msg)
            setattr(self, "original_message", deepcopy(msg))
        return getattr(self, "message")

    @override
    def get_plaintext(self) -> str:
        return self.get_message().extract_plain_text()

    @override
    def get_user_id(self) -> str:
        return self.from_user_id

    @override
    def get_session_id(self) -> str:
        return self.session_id or self.from_user_id

    @override
    def is_tome(self) -> bool:
        return self.to_me


class PrivateMessageEvent(MessageEvent):
    @override
    def get_event_name(self) -> str:
        return "message.private"

    @override
    def get_session_id(self) -> str:
        return f"private_{self.from_user_id}"
