"use client";

import { useEffect } from "react";

const artifact = "/downloads/AgentBridge-0.9.0.622-AutoCAD-2024.zip";

export default function LatestDownload() {
  useEffect(() => {
    window.location.replace(artifact);
  }, []);

  return (
    <main className="redirect-page">
      <div>
        <span>AGENTBRIDGE / LATEST RELEASE</span>
        <h1>正在准备下载…</h1>
        <p>如果下载没有自动开始，请使用下面的直接链接。</p>
        <a className="button primary" href={artifact} download>
          下载 AutoCAD 2024 插件 <b>↓</b>
        </a>
      </div>
    </main>
  );
}
