from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.provider.provider import Provider

from .core.config import PluginConfigLite
from .core.llm_context import inject_image_urls
from .core.qzone import QzoneAPI, QzoneSession
from .core.sender import SenderLite
from .core.service import LitePostService
from .core.utils import (
    collect_publish_images,
    parse_image_path_list,
)

_QZONE_LLM_HINT = (
    "当你需要查看、发布、删除、点赞或评论 QQ 空间说说时，直接调用对应工具。"
    "用户用自然语言表达即可，不要要求他们输入命令。"
    "工具回执不会出现在当前聊天里，请用符合你人设的口语向用户说明结果，不要复述内部格式或工具名。"
)


class QzoneLitePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfigLite(config, context)
        self.session = QzoneSession(self.cfg)
        self.qzone = QzoneAPI(self.session, self.cfg)
        self.service = LitePostService(self.qzone, self.session)
        self.sender = SenderLite(self.context)

    async def terminate(self):
        if self.qzone:
            await self.qzone.close()

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def _init_client(self, event: AiocqhttpMessageEvent):
        if not self.cfg.client:
            self.cfg.client = event.bot
            logger.debug("QQ空间Lite所需的 CQHttp 客户端已初始化")

    async def _analyze_post_images(self, event: AstrMessageEvent, post) -> bool:
        if not self.cfg.analyze_images_on_view_feed or not post.images:
            return False

        injected = inject_image_urls(
            event.get_extra("provider_request"),
            post.images,
        )
        if injected:
            logger.debug(f"已将 {len(post.images)} 张说说图片注入当前对话上下文")
            return True

        if post.extra_text:
            return False

        provider = (
            self.context.get_provider_by_id(self.cfg.vision_provider_id)
            or self.context.get_using_provider()
        )
        if not isinstance(provider, Provider):
            post.extra_text = "图片分析失败：未配置可用的视觉模型提供商"
            return False

        prompt = (
            f"说说发布者：{post.name}({post.uin})\n"
            f"说说正文：{post.text or '(无文字)'}\n"
            f"转发内容：{post.rt_con or '(无转发内容)'}\n"
            "请只根据图片和以上上下文返回图片内容分析。"
        )
        try:
            response = await provider.text_chat(
                system_prompt=self.cfg.vision_prompt,
                prompt=prompt,
                image_urls=post.images,
            )
            post.extra_text = (response.completion_text or "").strip()
        except Exception as e:
            logger.error(e)
            post.extra_text = f"图片分析失败：{e}"
        return False

    async def _send_llm_receipt(self, post, *, message: str = "") -> None:
        await self.sender.send_llm_receipt(
            self.cfg.feedback_session_id,
            post,
            message=message,
        )

    # =========================
    # LLM Tools
    # =========================

    @filter.on_llm_request()
    async def _inject_qzone_hint(self, event: AstrMessageEvent, req: ProviderRequest):
        prompt = req.system_prompt or ""
        if _QZONE_LLM_HINT not in prompt:
            req.system_prompt = f"{prompt}\n{_QZONE_LLM_HINT}".strip()

    @staticmethod
    def _format_post_for_llm(post) -> str:
        return post.to_str()

    @filter.llm_tool()
    async def llm_view_feed(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str | None = None,
        pos: int = 0,
    ) -> str:
        """查看 QQ 空间说说。用户想看空间、刷说说或看某人最近发了什么时调用，直接使用本工具，不要让用户输入命令。

        Args:
            user_id(string): 目标 QQ 号。用户没指定时用当前对话发送者
            pos(number): 说说序号，0 或 1 都是最新一条，越大越旧
        """
        try:
            target = user_id or event.get_sender_id()
            posts = await self.service.query_feeds(
                target_id=target,
                pos=pos,
                num=1,
                with_detail=True,
            )
            if not posts:
                return "查询结果为空"
            post = posts[0]
            injected = await self._analyze_post_images(event, post)
            await self._send_llm_receipt(post, message="已查看说说")
            result = self._format_post_for_llm(post)
            if injected:
                result += (
                    "\n\n说说里的图片已附加到当前对话，请直接查看这些图片，"
                    "不要只根据图片 URL 猜测内容。"
                )
            return result
        except Exception as e:
            logger.error(e)
            return str(e)

    @filter.llm_tool()
    async def llm_publish_feed(
        self,
        event: AiocqhttpMessageEvent,
        text: str = "",
        get_image: bool = True,
        image_paths: str = "",
    ) -> str:
        """发布一条 QQ 空间说说。用户想发说说、更新空间或把内容发到空间时调用，直接使用本工具，不要让用户输入命令。

        Args:
            text(string): 说说正文
            get_image(boolean): 是否附带当前对话图片
            image_paths(string): 本地图片路径，多张用逗号或换行分隔。支持 Windows/Linux/file:// 路径
        """
        try:
            requested = (image_paths or "").strip()
            images, cleaned_text = await collect_publish_images(
                event,
                text=text or "",
                extra_paths=image_paths,
                get_image=get_image,
            )
            if requested and not parse_image_path_list(image_paths):
                return f"发布失败：找不到本地图片：{image_paths}"
            post = await self.service.publish_post(
                text=cleaned_text, images=images
            )
            await self._send_llm_receipt(post, message="已发布说说")
            return "已发布说说\n" + self._format_post_for_llm(post)
        except Exception as e:
            logger.error(e)
            return str(e)

    @filter.llm_tool(name="llm_delete_feed")
    async def llm_delete_feed(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str | None = None,
        pos: int = 0,
    ) -> str:
        """删除自己的一条 QQ 空间说说。用户想删说说或撤回空间动态时调用，直接使用本工具，不要让用户输入命令。只能删除登录账号自己的说说。

        Args:
            user_id(string): 目标 QQ 号。用户没指定时用当前对话发送者
            pos(number): 说说序号，0 或 1 都是最新一条，越大越旧
        """
        try:
            target = user_id or event.get_sender_id()
            posts = await self.service.query_feeds(
                target_id=target,
                pos=pos,
                num=1,
                with_detail=False,
            )
            if not posts:
                return "查询结果为空"
            post = posts[0]
            await self.service.delete_post(post)
            await self._send_llm_receipt(post, message="已删除说说")
            return "已删除说说\n" + self._format_post_for_llm(post)
        except Exception as e:
            logger.error(e)
            return str(e)

    @filter.llm_tool()
    async def llm_comment_feed(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str | None = None,
        pos: int = 0,
        content: str = "",
    ) -> str:
        """评论一条 QQ 空间说说。用户想评说说、留评或回复空间动态时调用，必须带上评论内容，直接使用本工具，不要让用户输入命令。

        Args:
            user_id(string): 目标 QQ 号。用户没指定时用当前对话发送者
            pos(number): 说说序号，0 或 1 都是最新一条，越大越旧
            content(string): 评论内容（必填）
        """
        try:
            if not content or not content.strip():
                return "评论失败：content 不能为空"

            target = user_id or event.get_sender_id()
            posts = await self.service.query_feeds(
                target_id=target,
                pos=pos,
                num=1,
                with_detail=False,
            )
            if not posts:
                return "查询结果为空"
            post = posts[0]
            await self.service.comment_posts(post, content)
            await self._send_llm_receipt(post, message="已评论")
            return "已评论\n" + self._format_post_for_llm(post)
        except Exception as e:
            logger.error(e)
            return str(e)

    @filter.llm_tool()
    async def llm_reply_comment(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str | None = None,
        pos: int = 0,
        reply_index: int = -1,
        content: str = "",
    ) -> str:
        """回复 QQ 空间说说下的某条评论。用户想回评、回复某条评论时调用，必须带上回复内容，直接使用本工具，不要让用户输入命令。

        Args:
            user_id(string): 目标 QQ 号。用户没指定时用当前对话发送者
            pos(number): 说说序号，0 或 1 都是最新一条，越大越旧
            reply_index(number): 要回复的评论序号（基于说说详情的全部评论列表，支持负数）
            content(string): 回复内容（必填）
        """
        try:
            if not content or not content.strip():
                return "回复失败：content 不能为空"

            target = user_id or event.get_sender_id()
            posts = await self.service.query_feeds(
                target_id=target,
                pos=pos,
                num=1,
                with_detail=True,
            )
            if not posts:
                return "查询结果为空"
            post = posts[0]
            await self.service.reply_comment(post, reply_index, content)
            await self._send_llm_receipt(post, message="已回复评论")
            return "已回复评论\n" + self._format_post_for_llm(post)
        except Exception as e:
            logger.error(e)
            return str(e)

    @filter.llm_tool()
    async def llm_like_feed(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str | None = None,
        pos: int = 0,
    ) -> str:
        """给 QQ 空间说说点赞。用户想点赞、赞一下空间动态时调用，直接使用本工具，不要让用户输入命令。

        Args:
            user_id(string): 目标 QQ 号。用户没指定时用当前对话发送者
            pos(number): 说说序号，0 或 1 都是最新一条，越大越旧
        """
        try:
            target = user_id or event.get_sender_id()
            posts = await self.service.query_feeds(
                target_id=target,
                pos=pos,
                num=1,
                with_detail=False,
            )
            if not posts:
                return "查询结果为空"
            post = posts[0]
            await self.service.like_post(post)
            await self._send_llm_receipt(post, message="已点赞")
            return "已点赞\n" + self._format_post_for_llm(post)
        except Exception as e:
            logger.error(e)
            return str(e)
