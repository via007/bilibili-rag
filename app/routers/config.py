"""
LLM 配置管理路由

提供 LLM 配置的获取和更新接口
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm_factory import get_llm_config
from app.services.config_manager import update_llm_config, validate_provider

router = APIRouter(prefix="/config/llm", tags=["LLM 配置"])


class LLMConfigUpdate(BaseModel):
    """LLM 配置更新请求"""
    provider: Optional[str] = None
    model: Optional[str] = None
    embedding_model: Optional[str] = None


class LLMConfigResponse(BaseModel):
    """LLM 配置响应"""
    provider: str
    model: str
    embedding_model: str
    default_model: str
    available_providers: list[str]
    available_models: list[str]


@router.get("", response_model=LLMConfigResponse)
def get_llm_config_endpoint():
    """
    获取当前 LLM 配置信息

    返回当前使用的 LLM 厂商、模型、Embedding 模型，
    以及可用的厂商和模型列表。
    """
    return get_llm_config()


@router.put("")
def update_llm_config_endpoint(data: LLMConfigUpdate):
    """
    更新 LLM 配置

    支持更新：
    - provider: LLM 厂商
    - model: LLM 模型
    - embedding_model: Embedding 模型

    配置会写入 .env 文件持久化保存。
    重启服务后生效。
    """
    # 验证厂商是否有效
    if data.provider is not None:
        is_valid, error_msg = validate_provider(data.provider)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    # 验证模型是否有效（如果提供了）
    if data.model is not None and data.provider is not None:
        from app.services.providers import get_provider_models
        available_models = get_provider_models(data.provider)
        if available_models and data.model not in available_models:
            raise HTTPException(
                status_code=400,
                detail=f"模型 {data.model} 不在厂商 {data.provider} 的可用模型列表中"
            )

    # 更新配置
    success, message = update_llm_config(data.model_dump(exclude_none=True))

    if not success:
        raise HTTPException(status_code=500, detail=message)

    return {
        "success": True,
        "message": message,
        "note": "配置已保存到 .env 文件，重启服务后生效"
    }
