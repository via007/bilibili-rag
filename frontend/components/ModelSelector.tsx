"use client";

import { useState, useEffect } from "react";
import { configApi, LLMConfig, LLMConfigUpdate } from "@/lib/api";

// 厂商配置
const PROVIDERS = [
    { id: "dashscope", name: "阿里云 DashScope", models: ["qwen3-max", "qwen3-8b", "qwen3-32b", "qwen2.5-max", "qwen2.5-72b"] },
    { id: "baidu", name: "百度千帆", models: ["ernie-4.0-8k", "ernie-3.5-8k", "ernie-speed-8k"] },
    { id: "tencent", name: "腾讯混元", models: ["hunyuan-pro", "hunyuan-standard", "hunyuan-lite"] },
    { id: "volcengine", name: "字节火山引擎", models: ["doubao-pro-32k", "doubao-lite-4k"] },
    { id: "zhipu", name: "智谱 AI", models: ["glm-4-plus", "glm-4-flash", "glm-4"] },
    { id: "minimax", name: "MiniMax", models: ["abab6.5s-chat", "abab6.5g-chat"] },
    { id: "openai", name: "OpenAI", models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"] },
];

// Embedding 模型配置
const EMBEDDING_MODELS = [
    { id: "text-embedding-v4", name: "阿里云 Embedding V4" },
    { id: "text-embedding-3-large", name: "OpenAI Embedding V3 Large" },
    { id: "text-embedding-3-small", name: "OpenAI Embedding V3 Small" },
    { id: "bge-large-zh-v1.5", name: "BGE Large ZH V1.5" },
    { id: "bge-base-zh-v1.5", name: "BGE Base ZH V1.5" },
];

interface ModelSelectorProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function ModelSelector({ isOpen, onClose }: ModelSelectorProps) {
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [config, setConfig] = useState<LLMConfig | null>(null);
    const [formData, setFormData] = useState<LLMConfigUpdate>({
        provider: "dashscope",
        llm_model: "qwen3-max",
        embedding_model: "text-embedding-v4",
    });

    // 加载当前配置
    useEffect(() => {
        if (isOpen) {
            loadConfig();
        }
    }, [isOpen]);

    const loadConfig = async () => {
        setLoading(true);
        try {
            const data = await configApi.getLLMConfig();
            setConfig(data);
            setFormData({
                provider: data.provider,
                llm_model: data.llm_model,
                embedding_model: data.embedding_model,
            });
        } catch (error) {
            console.error("加载配置失败:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await configApi.updateLLMConfig(formData);
            onClose();
            alert("配置保存成功");
        } catch (error) {
            console.error("保存配置失败:", error);
            alert("保存失败，请检查后端是否已实现配置API");
        } finally {
            setSaving(false);
        }
    };

    const handleProviderChange = (providerId: string) => {
        const provider = PROVIDERS.find((p) => p.id === providerId);
        setFormData({
            ...formData,
            provider: providerId,
            llm_model: provider?.models[0] || "",
        });
    };

    if (!isOpen) return null;

    const currentProvider = PROVIDERS.find((p) => p.id === formData.provider);

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal-card model-selector-modal" onClick={(e) => e.stopPropagation()}>
                <div className="modal-header-custom">
                    <h2 className="modal-title">模型配置</h2>
                    <button className="btn-icon" onClick={onClose}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M18 6L6 18M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="modal-body-custom">
                    {loading ? (
                        <div className="loading-custom">加载中...</div>
                    ) : (
                        <>
                            <div className="form-group">
                                <label className="form-label">AI 厂商</label>
                                <select
                                    value={formData.provider}
                                    onChange={(e) => handleProviderChange(e.target.value)}
                                    className="input form-select"
                                >
                                    {PROVIDERS.map((p) => (
                                        <option key={p.id} value={p.id}>
                                            {p.name}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className="form-group">
                                <label className="form-label">对话模型</label>
                                <select
                                    value={formData.llm_model}
                                    onChange={(e) =>
                                        setFormData({ ...formData, llm_model: e.target.value })
                                    }
                                    className="input form-select"
                                >
                                    {currentProvider?.models.map((m) => (
                                        <option key={m} value={m}>
                                            {m}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className="form-group">
                                <label className="form-label">Embedding 模型</label>
                                <select
                                    value={formData.embedding_model}
                                    onChange={(e) =>
                                        setFormData({ ...formData, embedding_model: e.target.value })
                                    }
                                    className="input form-select"
                                >
                                    {EMBEDDING_MODELS.map((m) => (
                                        <option key={m.id} value={m.id}>
                                            {m.name}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {config && (
                                <div className="current-config">
                                    <span className="label">当前配置:</span>
                                    <span className="value">
                                        {PROVIDERS.find((p) => p.id === config.provider)?.name} / {config.llm_model}
                                    </span>
                                </div>
                            )}
                        </>
                    )}
                </div>

                <div className="modal-footer-custom">
                    <button className="btn btn-outline" onClick={onClose}>
                        取消
                    </button>
                    <button
                        className="btn btn-primary"
                        onClick={handleSave}
                        disabled={saving}
                    >
                        {saving ? "保存中..." : "保存配置"}
                    </button>
                </div>
            </div>
        </div>
    );
}
