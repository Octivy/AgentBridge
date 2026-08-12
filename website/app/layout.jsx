import "./globals.css";

export const metadata = {
  title: "AgentBridge｜让 AI 安全连接 AutoCAD",
  description:
    "面向 AutoCAD 2024 的 AI 连接器、CADMCP 服务与专业 Skill 基座。",
  openGraph: {
    title: "AgentBridge",
    description: "让 Codex、Claude 与企业模型安全读懂并操作 AutoCAD。",
    type: "website",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
