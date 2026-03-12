"""
Bilibili RAG 知识库系统

核心配置模块
"""
from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices
from loguru import logger
from decimal import Decimal, InvalidOperation
from typing import Optional
import os
import json


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
    # 按模型配置单价（每 1M tokens）：
    # {"qwen3.5-plus": {"input": 0.8, "output": 2.0}, "qwen3.5-flash": {"input": 0.3, "output": 0.6}}
    llm_model_prices_json: str = Field(default="{}", env="LLM_MODEL_PRICES_JSON")
    # 解析后的模型单价缓存，不从环境变量读取
    llm_model_prices: dict[str, dict[str, Decimal]] = Field(default_factory=dict, exclude=True)

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

    def model_post_init(self, __context) -> None:
        """在配置初始化后解析模型单价 JSON，避免请求路径重复解析。"""
        self.llm_model_prices = {}
        raw = (self.llm_model_prices_json or "").strip() or "{}"

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("LLM_MODEL_PRICES_JSON 解析失败，将按 0 费用记录: {}", e)
            return

        if not isinstance(parsed, dict):
            logger.warning(
                "LLM_MODEL_PRICES_JSON 必须是 JSON 对象，当前类型={}，将按 0 费用记录",
                type(parsed).__name__,
            )
            return

        for model_name, model_cfg in parsed.items():
            if not isinstance(model_name, str) or not isinstance(model_cfg, dict):
                continue

            input_raw = model_cfg.get("input_per_1m", model_cfg.get("input"))
            output_raw = model_cfg.get("output_per_1m", model_cfg.get("output"))
            if input_raw is None or output_raw is None:
                logger.warning("模型 {} 缺少 input/output 单价配置，已跳过", model_name)
                continue

            try:
                input_price = Decimal(str(input_raw))
                output_price = Decimal(str(output_raw))
            except (InvalidOperation, TypeError, ValueError):
                logger.warning("模型 {} 单价格式非法，已跳过", model_name)
                continue

            if input_price < 0 or output_price < 0:
                logger.warning("模型 {} 单价不能为负数，已跳过", model_name)
                continue

            self.llm_model_prices[model_name] = {
                "input": input_price,
                "output": output_price,
            }

        if self.llm_model_prices:
            logger.info("已加载 {} 个模型单价配置", len(self.llm_model_prices))
    
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
