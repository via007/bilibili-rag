"""
DynamicEmbeddings — 支持每次调用时动态解析 API Key 的 Embedding 包装器

用于 ChromaDB：Chroma 在 add/query 时会调用 embed_documents/embed_query，
此包装器在每次调用前根据 session_id 动态创建正确的 OpenAIEmbeddings 实例。

采用组合模式（不继承 OpenAIEmbeddings），避免 Pydantic v2 序列化冲突。
"""
from __future__ import annotations

import contextvars
import time
from typing import List, Optional

from langchain_openai import OpenAIEmbeddings
from loguru import logger

from app.config import settings


# ContextVar：每个请求独立存储当前 session_id
_embedding_session_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "embedding_session_id", default=None
)


class DynamicEmbeddings:
    """
    组合模式 Embedding 包装器。

    使用方式：
        embeddings = DynamicEmbeddings(api_key_manager, default_config)

        # 在异步请求上下文中设置 session_id
        _embedding_session_ctx.set(session_id)

        # Chroma 调用时会自动使用用户配置的 Key
        results = vectorstore.similarity_search("query")
    """

    def __init__(self, api_key_manager, **default_kwargs):
        """
        Args:
            api_key_manager: ApiKeyManager 实例（用于缓存查找和密文解密）
            **default_kwargs: 默认的 api_key, base_url, model
        """
        self._api_key_manager = api_key_manager
        self._default_api_key = default_kwargs.get("api_key", settings.openai_api_key)
        self._default_base_url = default_kwargs.get("base_url", settings.openai_base_url)
        self._default_model = default_kwargs.get("model", settings.embedding_model)

    def _make_embeddings(self) -> OpenAIEmbeddings:
        """根据 contextvar 中的 session_id 动态创建 OpenAIEmbeddings 实例。"""
        session_id = _embedding_session_ctx.get()
        api_key = self._default_api_key
        base_url = self._default_base_url
        model = self._default_model

        if session_id and self._api_key_manager.is_enabled:
            entry = self._api_key_manager._cache.get(session_id)
            if entry and entry.embedding_key_encrypted and entry.expire_at >= time.time():
                try:
                    api_key = self._api_key_manager._decrypt(entry.embedding_key_encrypted)
                    if entry.embedding_base_url:
                        base_url = entry.embedding_base_url
                    if entry.embedding_model:
                        model = entry.embedding_model
                except Exception as e:
                    logger.warning(f"[DYNAMIC_EMBED] failed to apply session config: {e}")

        return OpenAIEmbeddings(
            api_key=api_key,
            base_url=base_url,
            model=model,
            check_embedding_ctx_length=False,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表（Chroma add 时调用）。"""
        return self._make_embeddings().embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """嵌入查询文本（Chroma query 时调用）。"""
        return self._make_embeddings().embed_query(text)


def set_embedding_session(session_id: Optional[str]) -> None:
    """设置当前请求的 embedding session context。"""
    _embedding_session_ctx.set(session_id)


def get_embedding_session() -> Optional[str]:
    """获取当前请求的 embedding session context。"""
    return _embedding_session_ctx.get()
