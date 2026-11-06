import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Insight Hub",
  description: "多租户企业知识库 + AI Agent 工作台",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}