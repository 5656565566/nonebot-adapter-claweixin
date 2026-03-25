from typing import Type, Iterable, Optional
from typing_extensions import override

from nonebot.adapters import Message as BaseMessage, MessageSegment as BaseMessageSegment


class MessageSegment(BaseMessageSegment["Message"]):
    """
    ClaWeixin 协议 MessageSegment 适配
    依据 OpenClaw WeChat 协议定义 支持 TEXT, IMAGE, VOICE, FILE, VIDEO 等
    """

    @classmethod
    @override
    def get_message_class(cls) -> Type["Message"]:
        return Message

    @override
    def __str__(self) -> str:
        if self.is_text():
            return self.data.get("text", "")
        return f"[{self.type}:{self.data}]"

    @override
    def is_text(self) -> bool:
        return self.type == "text"

    @staticmethod
    def text(text: str) -> "Text":
        return Text("text", {"text": text})

    @staticmethod
    def image(url: Optional[str] = None, media: Optional[dict] = None, aeskey: Optional[str] = None) -> "Image":
        data = {}
        if url:
            data["url"] = url
        if media:
            data["media"] = media
        if aeskey:
            data["aeskey"] = aeskey
        return Image("image", data)

    @staticmethod
    def voice(text: Optional[str] = None, media: Optional[dict] = None) -> "Voice":
        data = {}
        if text:
            data["text"] = text
        if media:
            data["media"] = media
        return Voice("voice", data)

    @staticmethod
    def file(file_name: Optional[str] = None, media: Optional[dict] = None) -> "File":
        data = {}
        if file_name:
            data["file_name"] = file_name
        if media:
            data["media"] = media
        return File("file", data)

    @staticmethod
    def video(media: Optional[dict] = None) -> "Video":
        data = {}
        if media:
            data["media"] = media
        return Video("video", data)


class Text(MessageSegment):
    @override
    def __str__(self) -> str:
        return self.data["text"]


class Image(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[图片]"


class Voice(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[语音]"


class File(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[文件]"


class Video(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[视频]"


class Message(BaseMessage[MessageSegment]):
    """
    ClaWeixin 协议 Message 适配
    """

    @classmethod
    @override
    def get_segment_class(cls) -> Type[MessageSegment]:
        return MessageSegment

    @staticmethod
    @override
    def _construct(msg: str) -> Iterable[MessageSegment]:
        yield MessageSegment.text(msg)

    @classmethod
    def from_message_items(cls, items: list[dict]) -> "Message":
        """
        从 OpenClaw WeChat 的 MessageItem 列表构造 Message
        MessageItemType:
          NONE: 0,
          TEXT: 1,
          IMAGE: 2,
          VOICE: 3,
          FILE: 4,
          VIDEO: 5
        """
        msg = cls()
        for item in items:
            item_type = item.get("type")
            if item_type == 1 and "text_item" in item:
                msg.append(MessageSegment.text(item["text_item"].get("text", "")))
            elif item_type == 2 and "image_item" in item:
                img_data = item["image_item"]
                msg.append(MessageSegment.image(
                    url=img_data.get("url"),
                    media=img_data.get("media"),
                    aeskey=img_data.get("aeskey")
                ))
            elif item_type == 3 and "voice_item" in item:
                voice_data = item["voice_item"]
                msg.append(MessageSegment.voice(
                    text=voice_data.get("text"),
                    media=voice_data.get("media")
                ))
            elif item_type == 4 and "file_item" in item:
                file_data = item["file_item"]
                msg.append(MessageSegment.file(
                    file_name=file_data.get("file_name"),
                    media=file_data.get("media")
                ))
            elif item_type == 5 and "video_item" in item:
                video_data = item["video_item"]
                msg.append(MessageSegment.video(
                    media=video_data.get("media")
                ))
        return msg
