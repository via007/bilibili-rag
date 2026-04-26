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
    
    # OpenAI / LLM 配置
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DASHSCOPE_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")
    llm_model: str = Field(default="gpt-4-turbo", env="LLM_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", env="EMBEDDING_MODEL")
    eval_llm_model: str = Field(default="gpt-4o-mini", env="EVAL_LLM_MODEL")

    # Agentic RAG
    agentic_rag_top_k: int = Field(default=5, env="AGENTIC_RAG_TOP_K")
    agentic_rag_max_hops: int = Field(default=3, env="AGENTIC_RAG_MAX_HOPS")

    # LangSmith (用于 LangChain / LangGraph 自动追踪，无需代码改动)
    # 设置 LANGCHAIN_TRACING_V2=true 或 LANGSMITH_TRACING=true 并填入 API key 即可启用
    langchain_tracing_v2: bool = Field(default=False, env="LANGCHAIN_TRACING_V2")
    langsmith_tracing: bool = Field(default=False, env="LANGSMITH_TRACING")
    langsmith_api_key: str = Field(default="", env="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="bilibili-rag", env="LANGSMITH_PROJECT")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com", env="LANGSMITH_ENDPOINT")

    # DashScope ASR
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1",
        env="DASHSCOPE_BASE_URL"
    )
    asr_model: str = Field(default="paraformer-v2", env="ASR_MODEL")
    asr_timeout: int = Field(default=600, env="ASR_TIMEOUT")
    asr_model_local: str = Field(default="paraformer-realtime-v2", env="ASR_MODEL_LOCAL")
    asr_input_format: str = Field(default="pcm", env="ASR_INPUT_FORMAT")
    
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

    # 分块策略配置（Phase 1: 增强规则分块）
    chunk_target_size: int = Field(default=750, env="CHUNK_TARGET_SIZE")
    chunk_min_size: int = Field(default=300, env="CHUNK_MIN_SIZE")
    chunk_max_size: int = Field(default=900, env="CHUNK_MAX_SIZE")
    chunk_overlap: int = Field(default=100, env="CHUNK_OVERLAP")

    # Embedding 版本号（用于索引重建追踪）
    embedding_version: str = Field(default="v1", env="EMBEDDING_VERSION")

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
        "logs"
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
