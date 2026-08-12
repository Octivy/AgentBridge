# AgentBridge Website

AgentBridge 的产品官网与 AutoCAD 2024 插件下载页。

## 本地运行

```powershell
npm install
npm run dev
```

## 发布内容

- `public/downloads/AgentBridge-0.9.0.622-AutoCAD-2024.zip`
- `public/downloads/latest.json`
- `/download/latest` 永久入口
- `npm run build` 生成 Sites 所需的 `dist/server/index.js` 和托管元数据

插件压缩包来自主工程的 Release 构建。更新版本时必须同步修改首页版本号、
下载文件名、`latest.json` 与 `PackageContents.xml`。
