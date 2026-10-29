import copy
import re
from typing import Any

from astrbot.api import logger
from astrbot.core.provider.provider import Provider

from .config import PluginConfig
from .model import Comment, Post


class LLMAction:
    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.context = config.context

    @staticmethod
    def _join_prompt_parts(*parts: str) -> str:
        return "\n\n".join(part.strip() for part in parts if part and part.strip())

    @staticmethod
    def _get_event_umo(event: Any | None) -> str | None:
        umo = getattr(event, "unified_msg_origin", None)
        return str(umo) if umo else None

    def _get_event_platform_name(
        self, event: Any | None, umo: str | None = None
    ) -> str:
        getter = getattr(event, "get_platform_name", None)
        if callable(getter):
            try:
                platform_name = getter()
            except Exception:
                platform_name = None
            if platform_name:
                return str(platform_name)

        umo = umo or self._get_event_umo(event)
        if umo and ":" in umo:
            platform_id = umo.split(":", 1)[0]
            for platform in getattr(
                self.context.platform_manager, "platform_insts", []
            ):
                try:
                    meta = platform.meta()
                    if str(getattr(meta, "id", "")) == platform_id:
                        return str(getattr(meta, "name", "") or platform_id)
                except Exception:
                    continue
            return platform_id
        return ""

    def _get_provider_settings(
        self, event: Any | None, umo: str | None = None
    ) -> dict[str, Any]:
        umo = umo or self._get_event_umo(event)
        cfg = self.context.get_config(umo) if umo else self.context.get_config()
        provider_settings = cfg.get("provider_settings", {})
        return provider_settings if isinstance(provider_settings, dict) else {}

    def _get_provider(
        self,
        provider_id: str | None,
        event: Any | None = None,
        umo: str | None = None,
    ) -> Provider | None:
        provider = self.context.get_provider_by_id(provider_id) if provider_id else None
        if isinstance(provider, Provider):
            return provider

        try:
            umo = umo or self._get_event_umo(event)
            provider = (
                self.context.get_using_provider(umo)
                if umo
                else self.context.get_using_provider()
            )
        except Exception as e:
            logger.error(f"获取当前会话的 LLM 提供商失败: {e}")
            return None

        return provider if isinstance(provider, Provider) else None

    async def _get_persona_context(
        self, event: Any | None, umo: str | None = None
    ) -> tuple[str, list[dict[str, Any]]]:
        umo = umo or self._get_event_umo(event)
        if not umo:
            return "", []

        try:
            conversation_persona_id = None
            cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if cid:
                conversation = await self.context.conversation_manager.get_conversation(
                    umo, cid
                )
                if conversation:
                    conversation_persona_id = conversation.persona_id

            (
                persona_id,
                persona,
                _,
                _,
            ) = await self.context.persona_manager.resolve_selected_persona(
                umo=umo,
                conversation_persona_id=conversation_persona_id,
                platform_name=self._get_event_platform_name(event, umo),
                provider_settings=self._get_provider_settings(event, umo),
            )

            if not persona and persona_id:
                persona = self.context.persona_manager.get_persona_v3_by_id(persona_id)

            if not persona:
                return "", []

            persona_prompt = str(persona.get("prompt") or "").strip()
            begin_dialogs = copy.deepcopy(persona.get("_begin_dialogs_processed") or [])
            return persona_prompt, begin_dialogs
        except Exception as e:
            logger.warning(f"解析当前会话人格失败，将回退到插件默认任务提示词: {e}")
            return "", []

    async def _build_request_context(
        self,
        *,
        event: Any | None,
        task_prompt: str,
        contexts: list[dict[str, Any]] | None = None,
        umo: str | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        persona_prompt, persona_contexts = await self._get_persona_context(event, umo)
        system_prompt = self._join_prompt_parts(
            "# Persona Instructions\n\n" + persona_prompt if persona_prompt else "",
            task_prompt,
        )
        merged_contexts = [*persona_contexts]
        if contexts:
            merged_contexts.extend(contexts)
        return system_prompt, merged_contexts

    async def generate_comment(
        self, post: Post, *, event: Any | None = None, umo: str | None = None
    ) -> str | None:
        """根据帖子内容生成评论"""
        provider = self._get_provider(None, event, umo)
        if not isinstance(provider, Provider):
            logger.error("未配置用于文本生成任务的 LLM 提供商")
            return None
        try:
            content = post.text
            if post.rt_con:  # 转发文本
                content += f"\n[转发]\n{post.rt_con}"

            prompt = f"\n[帖子内容]：\n{content}"
            system_prompt, contexts = await self._build_request_context(
                event=event,
                task_prompt=self._join_prompt_parts(
                    self.cfg.llm.comment_prompt,
                    "# 输出要求：\n- 只输出最终评论内容，不要解释，不要分点，不要添加额外前缀。",
                ),
                umo=umo,
            )

            if self.cfg.debug_mode:
                logger.debug(prompt)
            # 先尝试带图片调用，若 LLM 不支持 vision 则降级为纯文本
            try:
                llm_response = await provider.text_chat(
                    system_prompt=system_prompt,
                    prompt=prompt,
                    contexts=contexts,
                    image_urls=post.images if post.images else None,
                )
            except Exception as img_err:
                err_msg = str(img_err).lower()
                if "image_url" in err_msg or "image" in err_msg:
                    logger.warning(
                        f"当前 LLM 不支持 vision，降级为纯文本评论: {img_err}"
                    )
                    llm_response = await provider.text_chat(
                        system_prompt=system_prompt,
                        prompt=prompt,
                        contexts=contexts,
                    )
                else:
                    raise
            comment = re.sub(r"[\s\u3000]+", "", llm_response.completion_text).rstrip(
                "。"
            )
            logger.info(f"LLM 生成的评论：{comment}")
            return comment

        except Exception as e:
            raise ValueError(f"LLM 调用失败：{e}")

    async def generate_reply(
        self,
        post: Post,
        comment: Comment,
        *,
        event: Any | None = None,
        umo: str | None = None,
    ) -> str | None:
        """根据评论内容生成回复"""
        provider = self._get_provider(None, event, umo)
        if not isinstance(provider, Provider):
            logger.error("未配置用于文本生成任务的 LLM 提供商")
            return None
        try:
            content = post.text
            if post.rt_con:  # 转发文本
                content += f"\n[转发]\n{post.rt_con}"

            prompt = f"\n## 帖子内容\n{content}"
            prompt += f"\n## 要回复的评论\n{comment.nickname}：{comment.content}"
            system_prompt, contexts = await self._build_request_context(
                event=event,
                task_prompt=self._join_prompt_parts(
                    self.cfg.llm.reply_prompt,
                    "# 输出要求：\n- 只输出最终回复内容，不要解释，不要分点，不要添加额外前缀。",
                ),
                umo=umo,
            )
            if self.cfg.debug_mode:
                logger.debug(prompt)
            llm_response = await provider.text_chat(
                system_prompt=system_prompt,
                prompt=prompt,
                contexts=contexts,
            )
            reply = re.sub(r"[\s\u3000]+", "", llm_response.completion_text).rstrip(
                "。"
            )
            logger.info(f"LLM 生成的回复：{reply}")
            return reply

        except Exception as e:
            raise ValueError(f"LLM 调用失败：{e}")
