# astrbot_plugin_qzone_lite

QQ 空间轻量插件，基于上游项目裁剪而来。
项目来源：<https://github.com/Zhalslar/astrbot_plugin_qzone>

当前版本只通过 AI 工具操作空间，没有用户指令：

- 看说说
- 发说说
- 删说说（仅删除自己的说说）
- 评说说（需提供评论内容）
- 回评（需提供回复内容）
- 赞说说

与上游相比，Lite 版本重点做了裁剪：去掉 DB 依赖、去掉 pillowmd 渲染链路；同时添加“评论/回复内容可自定义（显式传参）”能力，并修复了点赞功能，便于在轻量部署场景使用。

## LLM Tools

模型可按自然语言直接调用：

- `llm_view_feed(user_id: str | None = None, pos: int = 0)`
  - 查看目标用户指定序号的说说（默认当前会话发送者，`0` 为最新）。
- `llm_publish_feed(text: str = "", get_image: bool = True, image_paths: str = "")`
  - 发布说说。`image_paths` 可直接传本地图片路径（多张用逗号或换行分隔）；`get_image` 为是否附带当前对话图片。
- `llm_delete_feed(user_id: str | None = None, pos: int = 0)`
  - 删除指定说说，仅能删除自己的说说。
- `llm_comment_feed(user_id: str | None = None, pos: int = 0, content: str = "")`
  - 评论指定说说，`content` 必填。
- `llm_reply_comment(user_id: str | None = None, pos: int = 0, reply_index: int = -1, content: str = "")`
  - 回复指定评论，`content` 必填，`reply_index` 支持负数索引。
- `llm_like_feed(user_id: str | None = None, pos: int = 0)`
  - 点赞指定说说。

说明：
- 序号默认从 0/1 都可（两者都会指向最新一条）。
- `reply_index` 基于说说详情中的全部评论列表（包含自己的评论）。
- 发说说除了当前对话里的图片，也接受本地文件路径（Windows / Linux / `file://`，以及 `\AstrBot\data\...` 这种容器路径）。
- AI 调用工具时**不会**在当前聊天发送回执。结果只返回给模型，由模型用自然语言回复。
- 若配置了 `feedback_session_id`，回执会发到该会话（方便你在私聊/管理群核对）。
- 未配置回执会话时静默执行。
- 以上工具均依赖 QQ 空间登录态（Cookies / CQHTTP 会话）。
- 开启「查看说说时分析图片」后，会把说说图片注入当前对话，让支持视觉的模型直接看图；注入失败时才调用配置的视觉模型转成文字。

回执会话 ID 格式：`平台实例ID:消息类型:会话ID`，例如 `珂夜QQ:FriendMessage:123456789` 或 `珂夜QQ:GroupMessage:群号`。这里要用消息平台配置里的实例 ID，不一定是 `aiocqhttp`。

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

本项目基于 [GNU General Public License v3.0](LICENSE) 授权。
