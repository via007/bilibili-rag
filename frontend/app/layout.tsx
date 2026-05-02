import type { Metadata } from "next";
import { ZCOOL_XiaoWei, Noto_Sans_SC, Geist } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { ThemeProvider } from "@/components/ThemeProvider";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

const display = ZCOOL_XiaoWei({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-display",
});

const body = Noto_Sans_SC({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "BiliMind - 收藏夹知识库",
  description: "将你的 B站收藏夹变成可对话的知识库",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", type: "image/x-icon" },
    ],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={cn("font-sans", "dark", geist.variable)}>
      <body className={`${display.variable} ${body.variable} antialiased`}>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
