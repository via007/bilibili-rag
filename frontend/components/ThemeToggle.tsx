"use client";

import { Sun, Moon } from "lucide-react";
import { useTheme } from "./ThemeProvider";

export default function ThemeToggle({ className }: { className?: string }) {
    const { theme, toggle } = useTheme();

    return (
        <button
            onClick={toggle}
            className={className}
            title={theme === "dark" ? "切换到亮色模式" : "切换到暗色模式"}
            style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "36px",
                height: "36px",
                borderRadius: "10px",
                border: "1px solid var(--border)",
                background: "var(--card)",
                color: "var(--muted-foreground)",
                cursor: "pointer",
                transition: "all 0.2s ease",
                flexShrink: 0,
            }}
            onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--accent)";
                e.currentTarget.style.color = "var(--accent)";
            }}
            onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--border)";
                e.currentTarget.style.color = "var(--muted-foreground)";
            }}
        >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
    );
}
