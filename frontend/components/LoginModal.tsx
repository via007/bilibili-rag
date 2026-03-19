"use client";

import { useState, useEffect } from "react";
import { authApi, QRCodeResponse, UserInfo } from "@/lib/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (sessionId: string, user: UserInfo) => void;
}

export default function LoginModal({ isOpen, onClose, onSuccess }: Props) {
  const [qr, setQr] = useState<QRCodeResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "scanned" | "success" | "error">("loading");
  const [polling, setPolling] = useState(false);

  const getQR = async () => {
    setStatus("loading");
    try {
      const data = await authApi.getQRCode();
      setQr(data);
      setStatus("ready");
      setPolling(true);
    } catch {
      setStatus("error");
    }
  };

  useEffect(() => {
    if (isOpen) getQR();
    else {
      setPolling(false);
      setQr(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!polling || !qr) return;
    const timer = setInterval(async () => {
      try {
        const res = await authApi.pollQRCode(qr.qrcode_key);
        if (res.status === "scanned") setStatus("scanned");
        else if (res.status === "confirmed") {
          setPolling(false);
          setStatus("success");
          setTimeout(() => onSuccess(res.session_id!, res.user_info!), 500);
        } else if (res.status === "expired") {
          setPolling(false);
          setStatus("error");
        }
      } catch { }
    }, 2000);
    return () => clearInterval(timer);
  }, [polling, qr, onSuccess]);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">扫码登录</h2>
        <p className="modal-subtitle">使用哔哩哔哩 APP 扫描</p>

        <div className="mt-4 flex justify-center">
          {status === "loading" && (
            <div className="w-48 h-48 flex items-center justify-center rounded-2xl" style={{ border: '1px dashed var(--border-subtle)' }}>
              <div className="w-10 h-10 relative">
                <div className="absolute inset-0 rounded-full animate-spin" style={{ border: '3px solid transparent', borderTopColor: 'var(--accent)', animationDuration: '1s' }} />
                <div className="absolute inset-1 rounded-full animate-spin" style={{ border: '3px solid transparent', borderBottomColor: 'var(--accent)', animationDirection: 'reverse', animationDuration: '0.6s' }} />
              </div>
            </div>
          )}

          {(status === "ready" || status === "scanned") && qr && (
            <div className="relative">
              <img src={qr.qrcode_image_base64} alt="二维码" className="w-48 h-48 rounded-2xl" style={{ border: '1px solid var(--border-subtle)' }} />
              {status === "scanned" && (
                <div className="absolute inset-0 rounded-2xl flex flex-col items-center justify-center" style={{ backgroundColor: 'rgba(28, 28, 30, 0.95)' }}>
                  <div className="status-pill">已扫码</div>
                  <span className="text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>请在手机上确认</span>
                </div>
              )}
            </div>
          )}

          {status === "success" && (
            <div className="w-48 h-48 flex flex-col items-center justify-center">
              <div className="status-pill ok">登录成功</div>
              <p className="text-sm mt-3" style={{ color: 'var(--text-tertiary)' }}>正在进入工作台</p>
            </div>
          )}

          {status === "error" && (
            <div className="w-48 h-48 flex flex-col items-center justify-center">
              <p className="text-sm mb-3" style={{ color: 'var(--text-tertiary)' }}>二维码已过期</p>
              <button onClick={getQR} className="btn btn-primary">重新获取</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
