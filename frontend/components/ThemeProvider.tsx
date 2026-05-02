"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";

type Theme = "dark" | "light";

const ThemeContext = createContext<{
    theme: Theme;
    toggle: () => void;
}>({ theme: "dark", toggle: () => {} });

export function useTheme() {
    return useContext(ThemeContext);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
    const [theme, setTheme] = useState<Theme>("dark");

    useEffect(() => {
        const stored = localStorage.getItem("theme") as Theme | null;
        if (stored === "light" || stored === "dark") {
            setTheme(stored);
        }
    }, []);

    useEffect(() => {
        const root = document.documentElement;
        if (theme === "light") {
            root.classList.remove("dark");
        } else {
            root.classList.add("dark");
        }
        localStorage.setItem("theme", theme);
    }, [theme]);

    const toggle = useCallback(() => {
        setTheme((prev) => (prev === "dark" ? "light" : "dark"));
    }, []);

    return (
        <ThemeContext.Provider value={{ theme, toggle }}>
            {children}
        </ThemeContext.Provider>
    );
}
