/**
 * Providers - 客户端组件包裹
 */

"use client";

import { MantineProvider, createTheme } from "@mantine/core";
import { ToastProvider } from "./Toast";
import "@mantine/core/styles.css";

const theme = createTheme({
    primaryColor: "blue",
    fontFamily: "inherit",
    defaultRadius: "md",
    colors: {
        dark: [
            '#C1C2C5',
            '#A6A7AB',
            '#909296',
            '#5c5f66',
            '#373A40',
            '#2C2E33',
            '#25262B',
            '#1A1B1E',
            '#141517',
            '#101113',
        ],
    },
});

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <MantineProvider theme={theme} defaultColorScheme="dark">
            <ToastProvider />
            {children}
        </MantineProvider>
    );
}
