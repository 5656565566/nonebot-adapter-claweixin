import datetime
from copy import deepcopy
from typing import Any, Optional, List, Dict
from typing_extensions import override

from pydantic import BaseModel, Field, model_validator
from nonebot.adapters import Event as BaseEvent
from nonebot.compat import model_dump

from .message import Message


class Reply(BaseModel):
    ref_msg: dict[str, Any]

    @property
    def message(self) -> Message:
        """尝试将包含的回复信息解析为 Message"""
        item = self.ref_msg.get("message_item", {})
        return Message.from_message_items([item])

    async def get_origin(self) -> dict[str, Any]:
        return self.ref_msg


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
        message = getattr(self, "message", None) or self.get_message()
        message_id = getattr(self, "message_id", "")
        preview = str(message)
        if not preview:
            preview = "[空消息]"
        return f"Message {message_id} {preview}"

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

    media_data: Optional[bytes] = None
    media_type: Optional[str] = None
    file_name: Optional[str] = None

    message: Optional[Message] = None
    original_message: Optional[Message] = None

    @model_validator(mode="after")
    def populate_messages(self) -> "MessageEvent":
        if self.message is None:
            self.message = Message.from_message_items(
                self.item_list,
                media_data=self.media_data,
                file_name=self.file_name,
            )
        if self.original_message is None:
            self.original_message = deepcopy(self.message)
        return self

    @override
    def get_type(self) -> str:
        return "message"

    @override
    def get_message(self) -> Message:
        if self.message is None:
            self.message = Message.from_message_items(
                self.item_list,
                media_data=self.media_data,
                file_name=self.file_name,
            )
        if self.original_message is None:
            self.original_message = deepcopy(self.message)
        return self.message

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
