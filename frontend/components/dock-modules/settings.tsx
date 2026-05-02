"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, Star, ShieldCheck } from "lucide-react";
import { useDockContext } from "@/lib/dock-context";
import { credentialsApi, settingsApi, type CredentialItem, type CredentialCreateParams, type CredentialUpdateParams, type CredentialsStatus } from "@/lib/api";
import type { DockPanelProps } from "@/lib/dock-registry";
import CredentialForm from "./credential-form";

/* ──── Inline SVG Icons ──── */

function KeyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="8" cy="12" r="5.5" stroke="currentColor" strokeWidth="1.5" fill="currentColor" fillOpacity=".08"/>
      <path d="M12.5 12.5L20 20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M17 15l3 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
    </svg>
  );
}

function ProviderIcon({ provider }: { provider: string }) {
  if (provider === "openai") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="7" stroke="currentColor" strokeWidth="1.5" fill="currentColor" fillOpacity=".08"/>
        <path d="M8 14l3-4 2 4 3-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    );
  }
  if (provider === "anthropic") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="5" y="5" width="14" height="14" rx="4" stroke="currentColor" strokeWidth="1.5" fill="currentColor" fillOpacity=".06"/>
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" fill="currentColor" fillOpacity=".12"/>
      </svg>
    );
  }
  if (provider === "deepseek") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 3l9 7-9 7-9-7z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" fill="currentColor" fillOpacity=".08"/>
      </svg>
    );
  }
  return <KeyIcon />;
}

function InfoIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" fill="currentColor" fillOpacity=".06"/>
      <path d="M12 8v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <circle cx="12" cy="16.5" r=".8" fill="currentColor"/>
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.8" fill="none"/>
      <path d="M8 12l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2L2 22h20L12 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" fill="currentColor" fillOpacity=".08"/>
      <path d="M12 10v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <circle cx="12" cy="17.5" r=".8" fill="currentColor"/>
    </svg>
  );
}

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
        <line x1="1" y1="1" x2="23" y2="23"/>
      </svg>
    );
  }
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
}

/* ──── Legacy Config Section (Embedding / ASR) ──── */

function ConfigSection({
  title,
  description,
  icon,
  statusLabel,
  detailLines,
  statusChip,
  fields,
  isSaving,
  onSave,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  statusLabel: string;
  detailLines: string[];
  statusChip: React.ReactNode;
  fields: { label: string; placeholder: string; value: string; onChange: (v: string) => void; isKey?: boolean; alreadySet?: boolean }[];
  isSaving: boolean;
  onSave: () => void;
}) {
  const [visibleKeys, setVisibleKeys] = useState<Set<number>>(new Set());

  const toggleKey = (i: number) => {
    setVisibleKeys(prev => {
      const next = new Set(prev);
      if (next.has(i)) {
        next.delete(i);
      } else {
        next.add(i);
      }
      return next;
    });
  };

  return (
    <div className="sk-section">
      <div className="sk-section-head">
        {icon ? <span className="sk-section-icon">{icon}</span> : null}
        <div className="sk-section-titlebox">
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        {statusChip}
      </div>
        <div className="sk-config-layout">
        <div className="sk-config-aside">
          <div className="sk-config-badge">
            {icon ? <span className="sk-config-badge-icon">{icon}</span> : null}
            <div>
              <strong>{statusLabel}</strong>
              <span>{title} status</span>
            </div>
          </div>
          <p className="sk-config-copy">{description}</p>
          <div className="sk-config-points">
            {detailLines.map((line) => (
              <div key={line} className="sk-config-point">
                <span className="sk-config-point-dot" />
                <span>{line}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="sk-emb-fields">
          {fields.map((f, i) => (
            <div key={i} className="sk-field">
              <label>
                {f.label}
                {f.alreadySet && !f.value && (
                  <span className="sk-label-tag">already set</span>
                )}
              </label>
              {f.isKey ? (
                <div className="sk-input-wrap">
                  <input
                    type={visibleKeys.has(i) ? "text" : "password"}
                    value={f.value}
                    onChange={e => f.onChange(e.target.value)}
                    placeholder={f.alreadySet && !f.value ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022" : f.placeholder}
                    className="sk-input"
                  />
                  <button type="button" className="sk-eye" onClick={() => toggleKey(i)}>
                    <EyeIcon open={visibleKeys.has(i)} />
                  </button>
                </div>
              ) : (
                <input
                  type="text"
                  value={f.value}
                  onChange={e => f.onChange(e.target.value)}
                  placeholder={f.placeholder}
                  className="sk-input sk-input-text"
                />
              )}
            </div>
          ))}
          <button className="sk-btn sk-btn-primary" onClick={onSave} disabled={isSaving}>
            {isSaving ? "保存中\u2026" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ──── Main Component ──── */

export default function SettingsPanel({ isOpen }: DockPanelProps) {
  const ctx = useDockContext();
  const sessionId = ctx.sessionId;

  const [credentials, setCredentials] = useState<CredentialItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingCred, setEditingCred] = useState<CredentialItem | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // Legacy status
  const [status, setStatus] = useState<CredentialsStatus | null>(null);

  // Embedding state
  const [embApiKey, setEmbApiKey] = useState("");
  const [embBaseUrl, setEmbBaseUrl] = useState("");
  const [embModel, setEmbModel] = useState("");
  const [savingEmb, setSavingEmb] = useState(false);

  // ASR state
  const [asrApiKey, setAsrApiKey] = useState("");
  const [asrBaseUrl, setAsrBaseUrl] = useState("");
  const [asrModel, setAsrModel] = useState("");
  const [savingAsr, setSavingAsr] = useState(false);

  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const loadCredentials = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const data = await credentialsApi.list(sessionId);
      setCredentials(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const loadStatus = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await settingsApi.getCredentialsStatus(sessionId);
      setStatus(data);
      setEmbBaseUrl(data.embedding_base_url || "");
      setEmbModel(data.embedding_model || "");
      setAsrBaseUrl(data.asr_base_url || "");
      setAsrModel(data.asr_model || "");
    } catch { /* silent */ }
  }, [sessionId]);

  useEffect(() => {
    if (isOpen && sessionId) {
      loadCredentials();
      loadStatus();
    }
  }, [isOpen, sessionId, loadCredentials, loadStatus]);

  // ── Credential CRUD handlers ──

  const handleCreate = async (data: CredentialCreateParams | CredentialUpdateParams) => {
    if (!sessionId) return;
    await credentialsApi.create(sessionId, data as CredentialCreateParams);
    setShowForm(false);
    showToast("凭证已创建", "success");
    await loadCredentials();
  };

  const handleUpdate = async (data: CredentialCreateParams | CredentialUpdateParams) => {
    if (!sessionId || !editingCred) return;
    await credentialsApi.update(sessionId, editingCred.id, data as CredentialUpdateParams);
    setEditingCred(null);
    showToast("凭证已更新", "success");
    await loadCredentials();
  };

  const handleDelete = async (cred: CredentialItem) => {
    if (!sessionId) return;
    if (!confirm(`确定删除“${cred.name}”吗？此操作无法撤销。`)) return;
    await credentialsApi.delete(sessionId, cred.id);
    showToast("凭证已删除", "success");
    await loadCredentials();
  };

  const handleSetDefault = async (cred: CredentialItem) => {
    if (!sessionId) return;
    await credentialsApi.setDefault(sessionId, cred.id);
    showToast(`已将“${cred.name}”设为默认凭证`, "success");
    await loadCredentials();
  };

  // ── Embedding save ──

  const handleEmbSave = async () => {
    if (!sessionId) return;
    setSavingEmb(true);
    try {
      await settingsApi.setCredentials(sessionId, {
        ...(embApiKey && { embedding_api_key: embApiKey }),
        ...(embBaseUrl && { embedding_base_url: embBaseUrl }),
        ...(embModel && { embedding_model: embModel }),
      });
      setEmbApiKey("");
      showToast("Embedding 配置已保存", "success");
      await loadStatus();
    } catch (e) {
      showToast("保存失败：" + (e instanceof Error ? e.message : "未知错误"), "error");
    } finally {
      setSavingEmb(false);
    }
  };

  // ── ASR save ──

  const handleAsrSave = async () => {
    if (!sessionId) return;
    setSavingAsr(true);
    try {
      await settingsApi.setCredentials(sessionId, {
        ...(asrApiKey && { asr_api_key: asrApiKey }),
        ...(asrBaseUrl && { asr_base_url: asrBaseUrl }),
        ...(asrModel && { asr_model: asrModel }),
      });
      setAsrApiKey("");
      showToast("ASR 配置已保存", "success");
      await loadStatus();
    } catch (e) {
      showToast("保存失败：" + (e instanceof Error ? e.message : "未知错误"), "error");
    } finally {
      setSavingAsr(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="sk-panel">
      {/* Toast */}
      {toast && (
        <div className={`sk-toast ${toast.type}`}>
          <span className="sk-toast-icon">{toast.type === "success" ? <CheckIcon /> : <AlertIcon />}</span>
          {toast.message}
        </div>
      )}

      {/* ── Form overlay ── */}
      {(showForm || editingCred) && (
        <CredentialForm
          sessionId={sessionId!}
          credential={editingCred}
          onSave={editingCred ? handleUpdate : handleCreate}
          onCancel={() => { setShowForm(false); setEditingCred(null); }}
        />
      )}

      <div className="sk-head">
        <div>
          <span className="sk-kicker">凭证中心</span>
          <h2>API 凭证设置</h2>
          <p>统一管理对话、向量化与语音识别所使用的 API Key 和模型配置。</p>
        </div>
        <div className="sk-head-stat">
          <strong>{credentials.length}</strong>
          <span>LLM 凭证</span>
        </div>
      </div>

      <div className="sk-overview">
        <div className="sk-overview-card">
          <span className="sk-overview-icon"><KeyIcon /></span>
          <div>
            <strong>{credentials.length}</strong>
            <p>LLM API Key</p>
          </div>
        </div>
        <div className="sk-overview-card">
          <div>
            <strong>{status?.embedding_is_configured ? "已配置" : "待配置"}</strong>
            <p>向量化引擎</p>
          </div>
        </div>
        <div className="sk-overview-card">
          <div>
            <strong>{status?.asr_is_configured ? "已配置" : "待配置"}</strong>
            <p>语音识别服务</p>
          </div>
        </div>
      </div>

      {/* ── Section 1: LLM Credentials (multi) ── */}
      <div className="sk-section">
        <div className="sk-section-head">
          <span className="sk-section-icon"><KeyIcon /></span>
          <div className="sk-section-titlebox">
            <h3>LLM 凭证</h3>
            <p>支持配置多个服务商，并选择一个默认运行凭证。</p>
          </div>
          <button className="sk-add-btn" onClick={() => setShowForm(true)}>
            <Plus size={15} />
            <span>新增</span>
          </button>
        </div>

        {loading ? (
          <div className="sk-loading">加载中\u2026</div>
        ) : credentials.length === 0 ? (
          <div className="sk-empty">
            <p>当前还没有配置任何凭证。</p>
            <p className="sk-empty-sub">添加 API Key 后即可使用你自己的 LLM 服务商。</p>
          </div>
        ) : (
          <div className="sk-list">
            {credentials.map(cred => (
              <div key={cred.id} className={`sk-cred-card ${cred.is_default ? "is-default" : ""}`}>
                <div className="sk-cred-top">
                  <span className="sk-cred-icon"><ProviderIcon provider={cred.provider} /></span>
                  <div className="sk-cred-info">
                    <div className="sk-cred-name">
                      <span className="sk-cred-name-text">{cred.name}</span>
                      {cred.is_default && <span className="sk-default-badge"><ShieldCheck size={11} /> 默认</span>}
                    </div>
                    <div className="sk-cred-meta">
                      <span className="sk-provider-tag">{cred.provider}</span>
                      <span className="sk-masked">密钥：{cred.masked_key}</span>
                      {cred.default_model && <span className="sk-model">模型：{cred.default_model}</span>}
                    </div>
                  </div>
                </div>
                <div className="sk-cred-actions">
                  <button className="sk-act-btn" title="编辑" onClick={() => setEditingCred(cred)}>
                    <Pencil size={14} />
                  </button>
                  {!cred.is_default && (
                    <button className="sk-act-btn sk-act-star" title="设为默认" onClick={() => handleSetDefault(cred)}>
                      <Star size={14} />
                    </button>
                  )}
                  <button className="sk-act-btn sk-act-del" title="删除" onClick={() => handleDelete(cred)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Section 2: Embedding (single) ── */}
      <ConfigSection
        title="Embedding"
        description="用于知识库向量化、索引构建与检索召回的服务配置。"
        icon={null}
        statusLabel={status?.embedding_is_configured ? "已配置" : "待配置"}
        detailLines={[
          status?.embedding_is_configured
            ? `当前密钥：${status.embedding_masked_key || "已隐藏"}`
            : "当前还没有保存自定义 Embedding 密钥。",
          "修改模型后，建议重新构建知识库。",
          embBaseUrl || "如不修改，将继续使用默认接口地址。",
        ]}
        statusChip={
          status && (
            <span className={`sk-chip ${status.embedding_is_configured ? "on" : "off"}`}>
              {status.embedding_is_configured ? (
                <><CheckIcon /> {status.embedding_masked_key}</>
              ) : (
                <><AlertIcon /> 未配置</>
              )}
            </span>
          )
        }
        fields={[
          {
            label: "API Key", placeholder: "sk-\u2026", value: embApiKey, onChange: setEmbApiKey,
            isKey: true, alreadySet: status?.embedding_is_configured ?? false,
          },
          {
            label: "接口地址", placeholder: "https://api.openai.com/v1", value: embBaseUrl, onChange: setEmbBaseUrl,
          },
          {
            label: "模型", placeholder: "text-embedding-3-small", value: embModel, onChange: setEmbModel,
          },
        ]}
        isSaving={savingEmb}
        onSave={handleEmbSave}
      />

      {/* ── Section 3: ASR (single) ── */}
      <ConfigSection
        title="ASR（语音识别）"
        description="用于音频转写、字幕提取与语音内容识别的服务配置。"
        icon={null}
        statusLabel={status?.asr_is_configured ? "已配置" : "待配置"}
        detailLines={[
          status?.asr_is_configured
            ? `当前密钥：${status.asr_masked_key || "已隐藏"}`
            : "当前还没有保存自定义 ASR 密钥。",
          "用于音频转文字和字幕提取。",
          asrBaseUrl || "如不修改，将继续使用默认 ASR 接口地址。",
        ]}
        statusChip={
          status && (
            <span className={`sk-chip ${status.asr_is_configured ? "on" : "off"}`}>
              {status.asr_is_configured ? (
                <><CheckIcon /> {status.asr_masked_key}</>
              ) : (
                <><AlertIcon /> 未配置</>
              )}
            </span>
          )
        }
        fields={[
          {
            label: "API Key", placeholder: "sk-\u2026", value: asrApiKey, onChange: setAsrApiKey,
            isKey: true, alreadySet: status?.asr_is_configured ?? false,
          },
          {
            label: "接口地址", placeholder: "https://dashscope.aliyuncs.com/compatible-mode/v1", value: asrBaseUrl, onChange: setAsrBaseUrl,
          },
          {
            label: "模型", placeholder: "funasr-paraformer", value: asrModel, onChange: setAsrModel,
          },
        ]}
        isSaving={savingAsr}
        onSave={handleAsrSave}
      />

      {/* ── Notice (in scroll flow, NOT pinned) ── */}
      <div className="sk-note">
        <span className="sk-note-icon"><InfoIcon /></span>
        <div>
          <p>如果不配置你自己的密钥，系统会回退到共享默认配置，<strong>可能产生费用</strong>。</p>
          <p>修改 Embedding 模型后，通常需要重新构建知识库才能保持检索一致性。</p>
        </div>
      </div>

      <style jsx global>{`
        .sk-panel {
          height: 100%;
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 16px;
          padding: 22px;
          padding-bottom: 24px;
          overflow-y: auto;
          background:
            radial-gradient(circle at top right, rgba(6, 182, 212, 0.1), transparent 28%),
            linear-gradient(180deg, #161b22 0%, #21262d 100%);
          color: #e2e8f0;
          font-family: system-ui, -apple-system, sans-serif;
          position: relative;
        }

        /* ── Toast ── */
        .sk-toast {
          position: fixed;
          top: 12px;
          right: 14px;
          padding: 7px 14px;
          border-radius: 7px;
          font-size: 12.5px;
          font-weight: 500;
          z-index: 100;
          display: flex;
          align-items: center;
          gap: 7px;
          animation: skSlideIn .25s ease;
          backdrop-filter: blur(8px);
        }
        .sk-toast.success {
          background: rgba(34, 197, 94, 0.1);
          color: #4ade80;
          border: 1px solid rgba(34, 197, 94, 0.2);
          box-shadow: 0 10px 32px rgba(34, 197, 94, 0.08);
        }
        .sk-toast.error {
          background: rgba(248, 113, 113, 0.1);
          color: #f87171;
          border: 1px solid rgba(248, 113, 113, 0.2);
          box-shadow: 0 10px 32px rgba(248, 113, 113, 0.08);
        }
        .sk-toast-icon { display: flex; }
        @keyframes skSlideIn {
          from { opacity: 0; transform: translateY(-6px); }
          to   { opacity: 1; transform: translateY(0);   }
        }

        /* ── Header ── */
        .sk-head {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: flex-start;
          padding: 18px 18px 16px;
          border-radius: 18px;
          border: 1px solid rgba(48, 54, 61, 0.9);
          background:
            linear-gradient(135deg, rgba(22, 27, 34, 0.98) 0%, rgba(33, 38, 45, 0.94) 100%);
          box-shadow: 0 18px 40px rgba(0, 0, 0, 0.06);
        }
        .sk-kicker {
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
        .sk-head h2 {
          font-size: 17px;
          font-weight: 700;
          margin: 0 0 4px;
          letter-spacing: -0.02em;
        }
        .sk-head p {
          max-width: 540px;
          font-size: 12.5px;
          color: #8b949e;
          margin: 0;
        }
        .sk-head-stat {
          display: grid;
          gap: 2px;
          min-width: 108px;
          padding: 12px 14px;
          border-radius: 14px;
          background: linear-gradient(160deg, rgba(6, 182, 212, 0.08) 0%, rgba(6, 182, 212, 0.15) 100%);
          border: 1px solid rgba(6, 182, 212, 0.9);
          color: #22d3ee;
          text-align: right;
          box-shadow: inset 0 1px 0 rgba(22, 27, 34, 0.65);
        }
        .sk-head-stat strong {
          font-size: 22px;
          line-height: 1;
          font-weight: 700;
        }
        .sk-head-stat span {
          font-size: 11px;
          font-weight: 600;
          opacity: 0.88;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .sk-overview {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
        }
        .sk-overview-card {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px;
          border-radius: 18px;
          border: 1px solid rgba(48, 54, 61, 0.92);
          background: linear-gradient(180deg, #161b22 0%, #21262d 100%);
          box-shadow: 0 14px 32px rgba(0, 0, 0, 0.05);
        }
        .sk-overview-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 42px;
          height: 42px;
          border-radius: 14px;
          color: #06b6d4;
          background: rgba(6, 182, 212, 0.08);
          border: 1px solid rgba(6, 182, 212, 0.85);
          flex-shrink: 0;
        }
        .sk-overview-icon svg,
        .sk-section-icon svg,
        .sk-config-badge-icon svg,
        .sk-chip svg {
          display: block;
          flex-shrink: 0;
        }
        .sk-overview-card strong {
          display: block;
          font-size: 15px;
          font-weight: 700;
          color: #e2e8f0;
          letter-spacing: -0.02em;
        }
        .sk-overview-card p {
          margin: 2px 0 0;
          font-size: 12px;
          color: #8b949e;
          font-weight: 500;
        }

        /* ── Section ── */
        .sk-section {
          border: 1px solid rgba(48, 54, 61, 0.92);
          border-radius: 18px;
          background: rgba(22, 27, 34, 0.94);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          overflow: hidden;
          box-shadow: 0 14px 34px rgba(0, 0, 0, 0.05);
        }
        .sk-section-head {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 15px 18px;
          border-bottom: 1px solid rgba(48, 54, 61, 0.88);
          background: linear-gradient(180deg, rgba(33, 38, 45, 0.95) 0%, rgba(22, 27, 34, 0.92) 100%);
        }
        .sk-section-head h3 {
          font-size: 14px;
          font-weight: 700;
          margin: 0;
          letter-spacing: -0.02em;
        }
        .sk-section-titlebox {
          flex: 1;
          min-width: 0;
        }
        .sk-section-titlebox p {
          margin: 3px 0 0;
          font-size: 12px;
          color: #8b949e;
          line-height: 1.5;
        }
        .sk-section-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border-radius: 10px;
          color: #06b6d4;
          background: rgba(6, 182, 212, 0.08);
          border: 1px solid rgba(6, 182, 212, 0.55);
        }
        .sk-config-layout {
          display: grid;
          grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
          gap: 0;
        }
        .sk-config-aside {
          display: flex;
          flex-direction: column;
          gap: 14px;
          padding: 18px;
          background:
            linear-gradient(180deg, rgba(6, 182, 212, 0.06) 0%, rgba(33, 38, 45, 0.85) 100%);
          border-right: 1px solid rgba(48, 54, 61, 0.88);
        }
        .sk-config-badge {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px;
          border-radius: 16px;
          background: rgba(22, 27, 34, 0.72);
          border: 1px solid rgba(6, 182, 212, 0.92);
        }
        .sk-config-badge-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 42px;
          height: 42px;
          border-radius: 14px;
          color: #06b6d4;
          background: rgba(6, 182, 212, 0.1);
          border: 1px solid rgba(6, 182, 212, 0.8);
          flex-shrink: 0;
          line-height: 0;
        }
        .sk-config-badge strong {
          display: block;
          font-size: 15px;
          font-weight: 700;
          color: #e2e8f0;
          letter-spacing: -0.02em;
        }
        .sk-config-badge span {
          display: block;
          margin-top: 2px;
          font-size: 11px;
          color: #8b949e;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          font-weight: 700;
        }
        .sk-config-copy {
          margin: 0;
          font-size: 12.5px;
          line-height: 1.65;
          color: #8b949e;
        }
        .sk-config-points {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .sk-config-point {
          display: flex;
          align-items: flex-start;
          gap: 9px;
          font-size: 12px;
          color: #8b949e;
          line-height: 1.55;
        }
        .sk-config-point-dot {
          width: 7px;
          height: 7px;
          border-radius: 999px;
          background: #06b6d4;
          flex-shrink: 0;
          margin-top: 6px;
          box-shadow: 0 0 0 4px rgba(6, 182, 212, 0.14);
        }

        .sk-add-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 13px;
          border: 1px solid rgba(6, 182, 212, 0.95);
          border-radius: 10px;
          background: linear-gradient(180deg, #161b22 0%, #21262d 100%);
          color: #e2e8f0;
          font-size: 12.5px;
          font-weight: 650;
          cursor: pointer;
          transition: background .12s, border-color .12s, transform .12s, box-shadow .12s;
        }
        .sk-add-btn:hover {
          background: rgba(6, 182, 212, 0.08);
          border-color: #22d3ee;
          transform: translateY(-1px);
          box-shadow: 0 10px 24px rgba(6, 182, 212, 0.12);
        }

        /* ── Loading / Empty ── */
        .sk-loading {
          padding: 28px;
          text-align: center;
          font-size: 13px;
          color: #8b949e;
        }
        .sk-empty {
          padding: 30px 24px;
          text-align: center;
          background:
            radial-gradient(circle at top, rgba(6, 182, 212, 0.06), transparent 40%),
            transparent;
        }
        .sk-empty p {
          margin: 0;
          font-size: 13px;
          color: #8b949e;
          font-weight: 600;
        }
        .sk-empty-sub {
          font-size: 12px !important;
          color: #8b949e !important;
          margin-top: 6px !important;
          font-weight: 500 !important;
        }

        /* ── Credential cards ── */
        .sk-list {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          overflow-y: auto;
          gap: 14px;
          max-height: 360px;
          padding: 18px;
        }
        .sk-cred-card {
          display: flex;
          flex-direction: column;
          align-items: stretch;
          justify-content: space-between;
          padding: 16px;
          border: 1px solid rgba(48, 54, 61, 0.92);
          border-radius: 16px;
          transition: background .12s, transform .12s, box-shadow .12s, border-color .12s;
          gap: 12px;
          background: linear-gradient(180deg, #161b22 0%, #21262d 100%);
          min-width: 0;
        }
        .sk-cred-card.is-default {
          background:
            radial-gradient(circle at top right, rgba(34, 197, 94, 0.11), transparent 34%),
            linear-gradient(180deg, #161b22 0%, #21262d 100%);
          border-color: rgba(34, 197, 94, 0.25);
        }
        .sk-cred-card:hover {
          transform: translateY(-2px);
          border-color: rgba(6, 182, 212, 0.15);
          box-shadow: 0 14px 32px rgba(6, 182, 212, 0.1);
        }
        .sk-cred-card.is-default:hover {
          box-shadow: 0 16px 34px rgba(34, 197, 94, 0.12);
        }

        .sk-cred-top {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          min-width: 0;
          flex: 1;
        }
        .sk-cred-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 38px;
          height: 38px;
          border-radius: 12px;
          color: #06b6d4;
          background: rgba(6, 182, 212, 0.08);
          border: 1px solid rgba(6, 182, 212, 0.8);
          flex-shrink: 0;
        }
        .sk-cred-info {
          display: flex;
          flex-direction: column;
          gap: 4px;
          min-width: 0;
          flex: 1;
        }
        .sk-cred-name {
          font-size: 14px;
          font-weight: 700;
          display: flex;
          align-items: center;
          gap: 6px;
          min-width: 0;
        }
        .sk-cred-name-text {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sk-default-badge {
          display: inline-flex;
          align-items: center;
          gap: 3px;
          font-size: 10px;
          font-weight: 700;
          color: #4ade80;
          background: rgba(34, 197, 94, 0.15);
          padding: 3px 7px;
          border-radius: 999px;
          border: 1px solid rgba(34, 197, 94, 0.2);
          flex-shrink: 0;
        }
        .sk-cred-meta {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          font-size: 11.5px;
          color: #8b949e;
          flex-wrap: wrap;
        }
        .sk-provider-tag {
          font-weight: 700;
          color: #06b6d4;
          text-transform: capitalize;
          flex-shrink: 0;
          padding: 4px 8px;
          border-radius: 999px;
          background: rgba(6, 182, 212, 0.08);
        }
        .sk-masked {
          font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
          font-size: 11px;
          padding: 4px 8px;
          border-radius: 999px;
          background: #21262d;
          border: 1px solid rgba(48, 54, 61, 0.95);
        }
        .sk-model {
          font-size: 11px;
          color: #8b949e;
          padding: 4px 8px;
          border-radius: 999px;
          background: #21262d;
          border: 1px solid rgba(48, 54, 61, 0.95);
        }

        .sk-cred-actions {
          display: flex;
          justify-content: flex-end;
          gap: 6px;
          flex-shrink: 0;
        }
        .sk-act-btn {
          background: #161b22;
          border: 1px solid rgba(48, 54, 61, 0.95);
          padding: 8px;
          border-radius: 10px;
          cursor: pointer;
          color: #8b949e;
          display: flex;
          transition: color .12s, background .12s, border-color .12s, transform .12s;
        }
        .sk-act-btn:hover {
          color: #e2e8f0;
          background: rgba(6, 182, 212, 0.08);
          border-color: rgba(6, 182, 212, 0.15);
          transform: translateY(-1px);
        }
        .sk-act-star:hover {
          color: #fbbf24;
          border-color: rgba(251, 191, 36, 0.2);
          background: rgba(251, 191, 36, 0.1);
        }
        .sk-act-del:hover {
          color: #f87171;
          border-color: rgba(248, 113, 113, 0.2);
          background: rgba(248, 113, 113, 0.1);
        }

        /* ── Chip ── */
        .sk-chip {
          font-size: 11px;
          padding: 4px 10px;
          border-radius: 999px;
          font-weight: 700;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 5px;
          white-space: nowrap;
          border: 1px solid transparent;
          line-height: 1;
        }
        .sk-chip.on {
          background: rgba(34, 197, 94, 0.1);
          color: #4ade80;
          border-color: rgba(34, 197, 94, 0.2);
        }
        .sk-chip.off {
          background: rgba(251, 191, 36, 0.1);
          color: #fbbf24;
          border-color: rgba(251, 191, 36, 0.2);
        }

        /* ── Config fields (Embedding / ASR) ── */
        .sk-emb-fields {
          padding: 18px;
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
          background: rgba(22, 27, 34, 0.96);
        }

        /* ── Field ── */
        .sk-field {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .sk-field label {
          font-size: 11px;
          font-weight: 700;
          color: #8b949e;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .sk-label-tag {
          font-size: 10px;
          font-weight: 700;
          text-transform: none;
          letter-spacing: 0;
          color: #4ade80;
          background: rgba(34, 197, 94, 0.1);
          padding: 1px 6px;
          border-radius: 3px;
        }

        .sk-input {
          width: 100%;
          min-height: 42px;
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
        .sk-input-text {
          font-family: system-ui, -apple-system, sans-serif;
        }
        .sk-input::placeholder {
          font-family: system-ui, -apple-system, sans-serif;
          color: #8b949e;
        }
        .sk-input:focus {
          border-color: #22d3ee;
          background: #161b22;
          box-shadow: 0 0 0 4px rgba(34, 211, 238, 0.16);
        }

        .sk-input-wrap {
          position: relative;
          display: flex;
          align-items: center;
        }
        .sk-input-wrap .sk-input {
          padding-right: 36px;
        }
        .sk-eye {
          position: absolute;
          right: 6px;
          background: transparent;
          border: none;
          padding: 6px;
          cursor: pointer;
          color: #8b949e;
          display: flex;
          border-radius: 8px;
          transition: color .12s, background .12s;
        }
        .sk-eye:hover {
          color: #e2e8f0;
          background: rgba(48, 54, 61, 0.72);
        }

        /* ── Buttons ── */
        .sk-btn {
          padding: 9px 0;
          border: none;
          border-radius: 12px;
          font-size: 12.5px;
          font-weight: 700;
          cursor: pointer;
          transition: opacity .15s, background .15s, transform .1s, box-shadow .15s;
          letter-spacing: -0.02em;
          width: auto;
          min-width: 128px;
          justify-self: end;
          grid-column: 1 / -1;
          margin-top: 2px;
        }
        .sk-btn:active:not(:disabled) { transform: scale(0.98); }
        .sk-btn:disabled { opacity: 0.45; cursor: not-allowed; }
        .sk-btn-primary {
          background: linear-gradient(180deg, rgba(6, 182, 212, 0.18) 0%, rgba(6, 182, 212, 0.1) 100%);
          color: #22d3ee;
          border: 1px solid rgba(6, 182, 212, 0.25);
          box-shadow: 0 8px 18px rgba(6, 182, 212, 0.14);
        }
        .sk-btn-primary:hover:not(:disabled) {
          background: linear-gradient(180deg, rgba(6, 182, 212, 0.24) 0%, rgba(6, 182, 212, 0.14) 100%);
          box-shadow: 0 10px 20px rgba(6, 182, 212, 0.18);
        }

        /* ── Note (in scroll flow, NOT pinned to bottom) ── */
        .sk-note {
          font-size: 12px;
          color: #8b949e;
          padding: 14px 15px;
          background: linear-gradient(180deg, #21262d 0%, rgba(6, 182, 212, 0.08) 100%);
          border: 1px solid rgba(6, 182, 212, 0.9);
          border-radius: 16px;
          line-height: 1.7;
          display: flex;
          gap: 10px;
          box-shadow: inset 0 1px 0 rgba(22, 27, 34, 0.7);
        }
        .sk-note-icon {
          flex-shrink: 0;
          margin-top: 2px;
          color: #06b6d4;
        }
        .sk-note p {
          margin: 0 0 4px;
        }
        .sk-note p:last-child { margin-bottom: 0; }

        @media (max-width: 760px) {
          .sk-head {
            flex-direction: column;
          }
          .sk-head-stat {
            width: 100%;
            text-align: left;
          }
          .sk-overview,
          .sk-list,
          .sk-emb-fields {
            grid-template-columns: 1fr;
          }
          .sk-config-layout {
            grid-template-columns: 1fr;
          }
          .sk-config-aside {
            border-right: none;
            border-bottom: 1px solid rgba(48, 54, 61, 0.88);
          }
        }
      `}</style>
    </div>
  );
}
