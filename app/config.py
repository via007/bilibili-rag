"""
Bilibili RAG 知识库系统

核心配置模块
"""
from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置"""

    # LLM 厂商选择
    llm_provider: str = Field(default="minimax", env="LLM_PROVIDER")

    # OpenAI / LLM 配置
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DASHSCOPE_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")
    llm_model: str = Field(default="abab6.5s-chat", env="LLM_MODEL")
    embedding_model: str = Field(default="embo-1", env="EMBEDDING_MODEL")

    # DashScope 配置（默认厂商）
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env="DASHSCOPE_BASE_URL"
    )

    # 百度千帆
    baidu_api_key: str = Field(default="", env="BAIDU_API_KEY")
    baidu_base_url: str = Field(
        default="https://qianfan.baidubce.com/v2",
        env="BAIDU_BASE_URL"
    )

    # 腾讯混元
    tencent_api_key: str = Field(default="", env="TENCENT_API_KEY")
    tencent_base_url: str = Field(
        default="https://hunyuan.cloud.tencent.com/v1",
        env="TENCENT_BASE_URL"
    )

    # 字节火山引擎
    volcengine_api_key: str = Field(default="", env="VOLCENGINE_API_KEY")
    volcengine_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        env="VOLCENGINE_BASE_URL"
    )

    # 智谱 AI
    zhipu_api_key: str = Field(default="", env="ZHIPU_API_KEY")
    zhipu_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        env="ZHIPU_BASE_URL"
    )

    # MiniMax
    minimax_api_key: str = Field(default="", env="MINIMAX_API_KEY")
    minimax_base_url: str = Field(
        default="https://api.minimax.chat/v1",
        env="MINIMAX_BASE_URL"
    )
    asr_model: str = Field(default="paraformer-v2", env="ASR_MODEL")
    asr_timeout: int = Field(default=600, env="ASR_TIMEOUT")
    asr_model_local: str = Field(default="paraformer-realtime-v2", env="ASR_MODEL_LOCAL")
    asr_input_format: str = Field(default="pcm", env="ASR_INPUT_FORMAT")

    # 本地 ASR 配置（轻量化）
    asr_mode: str = Field(default="cloud", env="ASR_MODE")  # local/cloud/auto
    asr_backend: str = Field(default="whisper", env="ASR_BACKEND")  # whisper/funasr

    # Whisper 配置
    whisper_model_size: str = Field(default="base", env="WHISPER_MODEL_SIZE")
    whisper_language: str = Field(default="zh", env="WHISPER_LANGUAGE")
    whisper_quantize: bool = Field(default=True, env="WHISPER_QUANTIZE")

    # FunASR 配置（备选）
    funasr_model: str = Field(default="paraformer-tiny", env="FUNASR_MODEL")
    funasr_device: str = Field(default="cpu", env="FUNASR_DEVICE")
    funasr_model_dir: str = Field(default="./data/models", env="FUNASR_MODEL_DIR")

    # 质量评估配置
    asr_quality_threshold: float = Field(default=0.7, env="ASR_QUALITY_THRESHOLD")
    asr_low_confidence: float = Field(default=0.6, env="ASR_LOW_CONFIDENCE")
    
    # 应用配置
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")
    app_port: int = Field(default=8000, env="APP_PORT")
    debug: bool = Field(default=True, env="DEBUG")
    
    # 数据库
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bilibili_rag.db",
        env="DATABASE_URL"
    )
    
    # ChromaDB
    chroma_persist_directory: str = Field(
        default="./data/chroma_db",
        env="CHROMA_PERSIST_DIRECTORY"
    )

    # RAG 优化配置
    rag_multi_recall: bool = Field(default=True, env="RAG_MULTI_RECALL")
    rag_rerank: bool = Field(default=True, env="RAG_RERANK")
    rag_citation: bool = Field(default=True, env="RAG_CITATION")
    rerank_model: str = Field(default="BAAI/bge-reranker-base", env="RERANK_MODEL")

    # RRF 融合权重配置
    rrf_vector_weight: float = Field(default=0.5, env="RRF_VECTOR_WEIGHT")
    rrf_keyword_weight: float = Field(default=0.3, env="RRF_KEYWORD_WEIGHT")
    rrf_time_weight: float = Field(default=0.2, env="RRF_TIME_WEIGHT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局配置实例
settings = Settings()


def ensure_directories():
    """确保必要的目录存在"""
    dirs = [
        "data",
        settings.chroma_persist_directory,
        "logs",
        settings.funasr_model_dir,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
