"""WeiLink - Lightweight Python SDK for WeChat iLink Bot protocol."""

__version__ = "0.1.0"

from weilink.client import WeiLink
from weilink.models import BotInfo, Message, MessageType

__all__ = [
    "WeiLink",
    "BotInfo",
    "Message",
    "MessageType",
]
