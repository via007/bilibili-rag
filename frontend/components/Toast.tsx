/**
 * Toast 通知组件 - 基于 Sonner
 */

"use client";

import { Toaster as Sonner } from "sonner";

// 导出 toast 函数供其他地方使用
export { toast } from "sonner";

/**
 * Toast 提供者组件
 * 需要在 app 入口处包裹
 */
export function ToastProvider() {
    return (
        <Sonner
            theme="system"
            position="top-center"
            toastOptions={{
                style: {
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                },
            }}
        />
    );
}
