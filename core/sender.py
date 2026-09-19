from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.core.message.components import Plain
from astrbot.core.star.context import Context

if TYPE_CHECKING:
    from .model import Post


def normalize_feedback_session(session_id: str | None) -> str:
    return (session_id or "").strip()


def build_post_chain(post: Post, *, message: str = "") -> list:
    chain = []
    if message:
        chain.append(Plain(message))
    chain.append(Plain(post.to_str()))
    return chain


class SenderLite:
    def __init__(self, context: Context | None = None):
        self.context = context

    async def send_llm_receipt(
        self,
        session_id: str | None,
        post: Post,
        *,
        message: str = "",
    ) -> bool:
        session = normalize_feedback_session(session_id)
        if not session:
            return False
        if not self.context:
            logger.warning("无法发送空间回执：缺少 context")
            return False

        chain = MessageChain()
        if message:
            chain.message(message)
        chain.message(post.to_str())
        try:
            ok = await self.context.send_message(session, chain)
            if not ok:
                logger.error(f"发送空间回执失败：未找到会话对应平台 {session}")
            return bool(ok)
        except Exception as e:
            logger.error(f"发送空间回执失败: {e}")
            return False
