"use client";

import { useState } from "react";
import { Eye, EyeOff, X } from "lucide-react";
import type { CredentialItem, CredentialCreateParams, CredentialUpdateParams } from "@/lib/api";

/* ──── Provider config ──── */

const PROVIDERS: { value: string; label: string; placeholder_url: string }[] = [
  { value: "openai", label: "OpenAI", placeholder_url: "https://api.openai.com/v1" },
  { value: "anthropic", label: "Anthropic", placeholder_url: "https://api.anthropic.com" },
  { value: "deepseek", label: "DeepSeek", placeholder_url: "https://api.deepseek.com" },
  { value: "custom", label: "Custom", placeholder_url: "" },
];

/* ──── Props ──── */

export interface CredentialFormProps {
  sessionId: string;
  credential?: CredentialItem | null; // null = create mode
  onSave: (data: CredentialCreateParams | CredentialUpdateParams) => Promise<void>;
  onCancel: () => void;
}

/* ──── Component ──── */

export default function CredentialForm({ credential, onSave, onCancel }: CredentialFormProps) {
  const isEdit = !!credential;

  const [name, setName] = useState(credential?.name || "");
  const [provider, setProvider] = useState(credential?.provider || "openai");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(credential?.base_url || "");
  const [defaultModel, setDefaultModel] = useState(credential?.default_model || "");
  const [isDefault, setIsDefault] = useState(credential?.is_default || false);
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedProvider = PROVIDERS.find(p => p.value === provider);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) { setError("请输入名称"); return; }
    if (!isEdit && !apiKey.trim()) { setError("请输入 API Key"); return; }

    setSaving(true);
    try {
      const data: CredentialCreateParams | CredentialUpdateParams = {
        name: name.trim(),
        ...(isEdit ? {} : { provider }),
        ...(apiKey && { api_key: apiKey.trim() }),
        ...(baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
        ...(defaultModel.trim() ? { default_model: defaultModel.trim() } : {}),
        ...(isEdit ? {} : { is_default: isDefault }),
      };
      await onSave(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cf-overlay" onClick={onCancel}>
      <div className="cf-modal" onClick={e => e.stopPropagation()}>
        <div className="cf-head">
          <div>
            <span className="cf-kicker">{isEdit ? "更新配置" : "新增配置"}</span>
            <h3>{isEdit ? "编辑凭证" : "新增凭证"}</h3>
          </div>
          <button className="cf-close" onClick={onCancel}><X size={16} /></button>
        </div>

        <form onSubmit={handleSubmit} className="cf-body">
          {/* 名称 */}
          <div className="cf-field">
            <label>名称</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="例如：我的 OpenAI Key"
              className="cf-input"
              autoFocus
            />
          </div>

          {/* 服务商 */}
          <div className="cf-field">
            <label>服务商</label>
            <select
              value={provider}
              onChange={e => { setProvider(e.target.value); setBaseUrl(""); }}
              className="cf-input cf-select"
            >
              {PROVIDERS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {/* API Key */}
          <div className="cf-field">
            <label>
              API Key
              {isEdit && !apiKey && <span className="cf-label-tag">保持不变</span>}
            </label>
            <div className="cf-input-wrap">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder={isEdit && !apiKey ? "••••••••" : "sk-…"}
                className="cf-input"
              />
              <button type="button" className="cf-eye" onClick={() => setShowKey(!showKey)}>
                {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {/* 接口地址 */}
          <div className="cf-field">
            <label>接口地址</label>
            <input
              type="text"
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              placeholder={selectedProvider?.placeholder_url || ""}
              className="cf-input"
            />
          </div>

          {/* 默认模型 */}
          <div className="cf-field">
            <label>默认模型</label>
            <input
              type="text"
              value={defaultModel}
              onChange={e => setDefaultModel(e.target.value)}
              placeholder={provider === "openai" ? "gpt-4o" : provider === "anthropic" ? "claude-sonnet-4-6" : provider === "deepseek" ? "deepseek-chat" : ""}
              className="cf-input"
            />
          </div>

          {/* 设为默认（仅新增时显示） */}
          {!isEdit && (
            <label className="cf-check">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={e => setIsDefault(e.target.checked)}
              />
              <span>设为默认凭证</span>
            </label>
          )}

          {/* Error */}
          {error && <div className="cf-error">{error}</div>}

          {/* Actions */}
          <div className="cf-actions">
            <button type="button" className="cf-btn cf-btn-cancel" onClick={onCancel}>取消</button>
            <button type="submit" className="cf-btn cf-btn-save" disabled={saving}>
              {saving ? "保存中…" : "保存"}
            </button>
          </div>
        </form>
      </div>

      <style jsx>{`
        .cf-overlay {
          position: fixed;
          inset: 0;
          z-index: 9999;
          display: flex;
          align-items: center;
          justify-content: center;
          background:
            rgba(0, 0, 0, 0.6);
          backdrop-filter: blur(10px);
          animation: cfFadeIn .15s ease;
        }
        @keyframes cfFadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }

        .cf-modal {
          width: 440px;
          max-width: 92vw;
          max-height: 90vh;
          overflow-y: auto;
          background: linear-gradient(180deg, #161b22 0%, #21262d 100%);
          border: 1px solid rgba(48, 54, 61, 0.92);
          border-radius: 20px;
          box-shadow: 0 30px 80px rgba(0, 0, 0, 0.4);
          animation: cfSlideUp .2s ease;
        }
        @keyframes cfSlideUp {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        .cf-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          padding: 20px 22px 0;
        }
        .cf-kicker {
          display: inline-flex;
          align-items: center;
          margin-bottom: 8px;
          padding: 4px 10px;
          border-radius: 999px;
          background: rgba(6, 182, 212, 0.08);
          color: #06b6d4;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }
        .cf-head h3 {
          font-size: 18px;
          font-weight: 700;
          margin: 0;
          letter-spacing: -0.02em;
          color: #e2e8f0;
        }
        .cf-close {
          background: #161b22;
          border: 1px solid rgba(48, 54, 61, 0.95);
          cursor: pointer;
          color: #8b949e;
          padding: 8px;
          border-radius: 10px;
          display: flex;
          transition: color .12s, background .12s, border-color .12s, transform .12s;
        }
        .cf-close:hover {
          color: #e2e8f0;
          background: rgba(6, 182, 212, 0.08);
          border-color: rgba(6, 182, 212, 0.15);
          transform: translateY(-1px);
        }

        .cf-body {
          padding: 18px 22px 22px;
          display: flex;
          flex-direction: column;
          gap: 14px;
        }

        .cf-field {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .cf-field label {
          font-size: 11px;
          font-weight: 700;
          color: #8b949e;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .cf-label-tag {
          font-size: 10px;
          font-weight: 700;
          text-transform: none;
          letter-spacing: 0;
          color: #4ade80;
          background: rgba(34, 197, 94, 0.1);
          padding: 1px 6px;
          border-radius: 3px;
        }

        .cf-input {
          width: 100%;
          min-height: 44px;
          padding: 10px 12px;
          border: 1px solid #30363d;
          border-radius: 12px;
          font-size: 13px;
          background: #21262d;
          color: #e2e8f0;
          outline: none;
          transition: border-color .15s, box-shadow .15s, background .15s;
          font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
        }
        .cf-input::placeholder {
          font-family: system-ui, -apple-system, sans-serif;
          color: #8b949e;
        }
        .cf-input:focus {
          border-color: #22d3ee;
          background: #161b22;
          box-shadow: 0 0 0 4px rgba(34, 211, 238, 0.16);
        }
        .cf-select {
          font-family: system-ui, -apple-system, sans-serif;
          cursor: pointer;
        }

        .cf-input-wrap {
          position: relative;
          display: flex;
          align-items: center;
        }
        .cf-input-wrap .cf-input {
          padding-right: 36px;
        }
        .cf-eye {
          position: absolute;
          right: 6px;
          background: transparent;
          border: none;
          padding: 6px;
          cursor: pointer;
          color: #8b949e;
          display: flex;
          border-radius: 8px;
        }
        .cf-eye:hover {
          color: #e2e8f0;
          background: rgba(48, 54, 61, 0.72);
        }

        .cf-check {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: #8b949e;
          cursor: pointer;
          padding: 6px 0 2px;
          font-weight: 600;
        }
        .cf-check input {
          width: 16px;
          height: 16px;
          accent-color: #06b6d4;
        }

        .cf-error {
          font-size: 12.5px;
          color: #f87171;
          padding: 10px 12px;
          background: rgba(248, 113, 113, 0.1);
          border-radius: 12px;
          border: 1px solid rgba(248, 113, 113, 0.2);
        }

        .cf-actions {
          display: flex;
          gap: 10px;
          padding-top: 6px;
        }
        .cf-btn {
          flex: 1;
          min-height: 40px;
          padding: 8px 0;
          border: none;
          border-radius: 12px;
          font-size: 12.5px;
          font-weight: 700;
          cursor: pointer;
          transition: opacity .15s, background .15s, transform .1s, box-shadow .15s, border-color .15s;
        }
        .cf-btn:active:not(:disabled) { transform: scale(0.98); }
        .cf-btn:disabled { opacity: 0.45; cursor: not-allowed; }
        .cf-btn-save {
          flex: 0 0 116px;
          background: linear-gradient(180deg, rgba(6, 182, 212, 0.18) 0%, rgba(6, 182, 212, 0.1) 100%);
          color: #22d3ee;
          border: 1px solid rgba(6, 182, 212, 0.25);
          box-shadow: 0 8px 18px rgba(6, 182, 212, 0.14);
        }
        .cf-btn-save:hover:not(:disabled) {
          background: linear-gradient(180deg, rgba(6, 182, 212, 0.24) 0%, rgba(6, 182, 212, 0.14) 100%);
          box-shadow: 0 10px 20px rgba(6, 182, 212, 0.18);
        }
        .cf-btn-cancel {
          background: #161b22;
          color: #8b949e;
          border: 1px solid rgba(48, 54, 61, 0.95);
        }
        .cf-btn-cancel:hover:not(:disabled) {
          background: rgba(6, 182, 212, 0.08);
          border-color: rgba(6, 182, 212, 0.15);
        }
      `}</style>
    </div>
  );
}
