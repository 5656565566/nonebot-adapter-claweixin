import datetime
from copy import deepcopy
from typing import Any, Optional, TYPE_CHECKING
from typing_extensions import override

from pydantic import BaseModel
from nonebot.adapters import Event as BaseEvent
from nonebot.compat import model_dump

from .message import Message


class Event(BaseEvent):
    time: datetime.datetime

    @override
    def get_type(self) -> str:
        raise NotImplementedError

    @override
    def get_event_name(self) -> str:
        raise NotImplementedError

    @override
    def get_event_description(self) -> str:
        return str(model_dump(self))

    @override
    def get_message(self) -> Message:
        raise NotImplementedError

    @override
    def get_plaintext(self) -> str:
        raise NotImplementedError

    @override
    def get_user_id(self) -> str:
        raise NotImplementedError

    @override
    def get_session_id(self) -> str:
        raise NotImplementedError

    @override
    def is_tome(self) -> bool:
        return False


class MessageEvent(Event):
    to_me: bool = False
    reply: Optional[Any] = None
    message_id: str
    
    if TYPE_CHECKING:
        message: Message
        original_message: Message
        
    @override
    def get_message(self) -> Message:
        if not hasattr(self, "message"):
            msg = Message() # 实际上应从原始数据构造
            setattr(self, "message", msg)
            setattr(self, "original_message", deepcopy(msg))
        return getattr(self, "message")

    @override
    def is_tome(self) -> bool:
        return self.to_me
