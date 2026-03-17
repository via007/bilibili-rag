"""
LLM 厂商 Provider 抽象基类和实现

支持多厂商 LLM：DashScope, Baidu, Tencent, VolcEngine, Zhipu, MiniMax, OpenAI
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from app.config import settings


# ============== 模型映射表 ==============

PROVIDER_MODELS: Dict[str, Dict[str, Any]] = {
    "dashscope": {
        "default": "qwen3-max",
        "models": ["qwen3-max", "qwen3-plus", "qwen3", "qwen-turbo", "qwen2.5-coder-32b-instruct"],
        "embedding": "text-embedding-v3"
    },
    "baidu": {
        "default": "ernie-4.0-8k",
        "models": ["ernie-4.0-8k", "ernie-3.5-8k", "ernie-speed-8k"],
        "embedding": "embedding-v1"
    },
    "tencent": {
        "default": "hunyuan-pro",
        "models": ["hunyuan-pro", "hunyuan-standard", "hunyuan-lite"],
        "embedding": "embedding-1"
    },
    "volcengine": {
        "default": "doubao-pro-4k",
        "models": ["doubao-pro-4k", "doubao-lite-4k", "doubao-pro-32k"],
        "embedding": "doubao-embedding"
    },
    "zhipu": {
        "default": "glm-4",
        "models": ["glm-4", "glm-4-flash", "glm-4-plus", "glm-3-turbo"],
        "embedding": "embedding-3"
    },
    "minimax": {
        "default": "abab6.5s-chat",
        "models": ["abab6.5s-chat", "abab6.5g-chat", "abab5.5s-chat", "abab6.5-chat"],
        "embedding": "embo-1"
    },
    "openai": {
        "default": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "embedding": "text-embedding-3-small"
    }
}


# ============== 抽象基类 ==============

class LLMProvider(ABC):
    """LLM 厂商抽象基类"""

    @abstractmethod
    def get_api_key(self) -> str:
        """获取 API Key"""
        pass

    @abstractmethod
    def get_base_url(self) -> str:
        """获取 Base URL"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型"""
        pass

    @abstractmethod
    def get_embedding_model(self) -> str:
        """获取 Embedding 模型"""
        pass


# ============== 各厂商实现 ==============

class DashScopeProvider(LLMProvider):
    """阿里云 DashScope"""

    def get_api_key(self) -> str:
        # 兼容旧的 DASHSCOPE_API_KEY 配置（通过 openai_api_key 的 AliasChoices）
        return settings.openai_api_key

    def get_base_url(self) -> str:
        return settings.dashscope_base_url

    def get_default_model(self) -> str:
        return PROVIDER_MODELS["dashscope"]["default"]

    def get_embedding_model(self) -> str:
        return PROVIDER_MODELS["dashscope"]["embedding"]


class BaiduProvider(LLMProvider):
    """百度千帆"""

    def get_api_key(self) -> str:
        return settings.baidu_api_key

    def get_base_url(self) -> str:
        return settings.baidu_base_url

    def get_default_model(self) -> str:
        return PROVIDER_MODELS["baidu"]["default"]

    def get_embedding_model(self) -> str:
        return PROVIDER_MODELS["baidu"]["embedding"]


class TencentProvider(LLMProvider):
    """腾讯混元"""

    def get_api_key(self) -> str:
        return settings.tencent_api_key

    def get_base_url(self) -> str:
        return settings.tencent_base_url

    def get_default_model(self) -> str:
        return PROVIDER_MODELS["tencent"]["default"]

    def get_embedding_model(self) -> str:
        return PROVIDER_MODELS["tencent"]["embedding"]


class VolcEngineProvider(LLMProvider):
    """字节火山引擎"""

    def get_api_key(self) -> str:
        return settings.volcengine_api_key

    def get_base_url(self) -> str:
        return settings.volcengine_base_url

    def get_default_model(self) -> str:
        return PROVIDER_MODELS["volcengine"]["default"]

    def get_embedding_model(self) -> str:
        return PROVIDER_MODELS["volcengine"]["embedding"]


class ZhipuProvider(LLMProvider):
    """智谱 AI"""

    def get_api_key(self) -> str:
        return settings.zhipu_api_key

    def get_base_url(self) -> str:
        return settings.zhipu_base_url

    def get_default_model(self) -> str:
        return PROVIDER_MODELS["zhipu"]["default"]

    def get_embedding_model(self) -> str:
        return PROVIDER_MODELS["zhipu"]["embedding"]


class MiniMaxProvider(LLMProvider):
    """MiniMax"""

    def get_api_key(self) -> str:
        return settings.minimax_api_key

    def get_base_url(self) -> str:
        return settings.minimax_base_url

    def get_default_model(self) -> str:
        return PROVIDER_MODELS["minimax"]["default"]

    def get_embedding_model(self) -> str:
        return PROVIDER_MODELS["minimax"]["embedding"]


class OpenAIProvider(LLMProvider):
    """OpenAI"""

    def get_api_key(self) -> str:
        return settings.openai_api_key

    def get_base_url(self) -> str:
        return settings.openai_base_url

    def get_default_model(self) -> str:
        return PROVIDER_MODELS["openai"]["default"]

    def get_embedding_model(self) -> str:
        return PROVIDER_MODELS["openai"]["embedding"]


# ============== Provider 注册表 ==============

PROVIDER_MAP: Dict[str, LLMProvider] = {
    "dashscope": DashScopeProvider(),
    "baidu": BaiduProvider(),
    "tencent": TencentProvider(),
    "volcengine": VolcEngineProvider(),
    "zhipu": ZhipuProvider(),
    "minimax": MiniMaxProvider(),
    "openai": OpenAIProvider(),
}


def get_provider(provider: Optional[str] = None) -> LLMProvider:
    """获取指定厂商的 Provider"""
    provider = provider or settings.llm_provider
    if provider not in PROVIDER_MAP:
        raise ValueError(f"不支持的 LLM 厂商: {provider}，支持: {list(PROVIDER_MAP.keys())}")
    return PROVIDER_MAP[provider]


def get_available_providers() -> List[str]:
    """获取可用的厂商列表"""
    return list(PROVIDER_MAP.keys())


def get_provider_models(provider: str) -> List[str]:
    """获取指定厂商的模型列表"""
    if provider not in PROVIDER_MODELS:
        return []
    return PROVIDER_MODELS[provider].get("models", [])
