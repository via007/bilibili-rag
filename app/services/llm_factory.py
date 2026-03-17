"""
LLM 和 Embedding 客户端工厂函数

根据配置动态创建 LLM 和 Embedding 客户端
"""
from typing import Optional, List
from langchain.embeddings.base import Embeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI
from app.config import settings
from app.services import providers


class DashScopeEmbeddings(Embeddings):
    """
    DashScope Embedding 客户端

    直接使用 OpenAI SDK 避免 LangChain OpenAIEmbeddings 的兼容性问题
    """

    def __init__(
        self,
        model: str = "text-embedding-v3",
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ):
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量 embedding"""
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [d.embedding for d in response.data]

    def embed_query(self, text: str) -> List[float]:
        """单条文本 embedding"""
        return self.embed_documents([text])[0]


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.5
) -> ChatOpenAI:
    """
    获取 LLM 客户端

    Args:
        provider: 厂商名称，默认使用 settings.llm_provider
        model: 模型名称，默认使用 settings.llm_model
        temperature: 温度参数

    Returns:
        ChatOpenAI 客户端实例
    """
    provider = provider or settings.llm_provider
    model = model or settings.llm_model

    provider_obj = providers.get_provider(provider)

    api_key = provider_obj.get_api_key()
    # 确保 api_key 是字符串类型
    if hasattr(api_key, 'get_secret_value'):
        api_key = api_key.get_secret_value()
    if not api_key:
        raise ValueError(f"厂商 {provider} 的 API Key 未配置，请检查环境变量")

    base_url = provider_obj.get_base_url()

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        streaming=False,
        request_timeout=300,
        max_tokens=4000
    )


def get_embeddings_client(
    provider: Optional[str] = None,
    model: Optional[str] = None
) -> Embeddings:
    """
    获取 Embedding 客户端

    Args:
        provider: 厂商名称，默认使用 settings.llm_provider
        model: Embedding 模型名称，默认使用 settings.embedding_model

    Returns:
        Embeddings 客户端实例
    """
    provider = provider or settings.llm_provider
    model = model or settings.embedding_model

    provider_obj = providers.get_provider(provider)

    api_key = provider_obj.get_api_key()
    # 确保 api_key 是字符串类型
    if hasattr(api_key, 'get_secret_value'):
        api_key = api_key.get_secret_value()
    if not api_key:
        raise ValueError(f"厂商 {provider} 的 API Key 未配置，请检查环境变量")

    base_url = provider_obj.get_base_url()

    # 对于 DashScope，使用自定义的 Embeddings 类避免兼容性问题
    if provider == "dashscope":
        return DashScopeEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url
        )

    # 其他厂商使用 OpenAIEmbeddings
    return OpenAIEmbeddings(
        api_key=api_key,
        base_url=base_url,
        model=model
    )


def get_llm_config() -> dict:
    """
    获取当前 LLM 配置信息

    Returns:
        包含当前配置信息的字典
    """
    provider = settings.llm_provider
    provider_obj = providers.get_provider(provider)

    return {
        "provider": provider,
        "model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "default_model": provider_obj.get_default_model(),
        "available_providers": providers.get_available_providers(),
        "available_models": providers.get_provider_models(provider)
    }
