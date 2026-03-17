"""
配置管理服务

负责配置的持久化和验证
"""
import os
from typing import Dict, Optional, Tuple

from app.config import settings
from app.services import providers


def validate_provider(provider: str) -> Tuple[bool, Optional[str]]:
    """
    验证 LLM 厂商是否有效

    Args:
        provider: 厂商名称

    Returns:
        (是否有效, 错误信息)
    """
    available = providers.get_available_providers()
    if provider not in available:
        return False, f"不支持的厂商: {provider}，支持的厂商: {available}"
    return True, None


def update_llm_config(config: Dict[str, str]) -> Tuple[bool, str]:
    """
    更新 LLM 配置并写入 .env 文件

    Args:
        config: 配置字典，如 {"provider": "dashscope", "model": "qwen3-max"}

    Returns:
        (是否成功, 消息)
    """
    if not config:
        return False, "没有需要更新的配置"

    # 环境变量映射
    env_mapping = {
        "provider": "LLM_PROVIDER",
        "model": "LLM_MODEL",
        "embedding_model": "EMBEDDING_MODEL",
    }

    # 读取现有 .env 文件
    env_file = ".env"
    env_vars: Dict[str, str] = {}

    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env_vars[key] = value

    # 更新配置
    updated_keys = []
    for config_key, env_key in env_mapping.items():
        if config_key in config:
            env_vars[env_key] = config[config_key]
            updated_keys.append(f"{env_key}={config[config_key]}")

    # 写回 .env 文件
    with open(env_file, "w", encoding="utf-8") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")

    return True, f"配置已更新: {', '.join(updated_keys)}"
