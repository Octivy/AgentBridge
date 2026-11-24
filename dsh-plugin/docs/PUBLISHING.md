# 发布 AgentBridge 插件到 DeepSeek Harness 插件生态

DeepSeek Harness 的第三方插件生态是 **npm 注册表 + 插件市场索引**，没有中心商店。
要让同事"搜得到、装得上"，需要三步：**打包 → 发布 → 提供索引地址**。

## 一、理解机制

- **安装来源**：插件可以来自 npm（`name@version`）或 Git 仓库（`git+https://...git#<commit>&path:/<目录>`）。
- **市场索引**：一个 JSON 文件（格式 1），列出可安装的插件及其版本/图标/描述。本目录的
  `market-index.json` 就是它。
- **用户侧**：同事在 DSH 里打开 **插件 → 发现（Discover）→ 管理索引源 → 添加索引地址**，
  然后搜索 "agentbridge" 即可安装。

## 二、发布步骤（Git 方式，无需 npm 账号）

1. **提交插件到仓库**：把本目录（`dsh-plugin/`，含 `runtime/`、`cordis.patch.yml`、`market-index.json`）
   提交到 `github.com/Octivy/Agent_Bridge` 的 `dsh-plugin/` 目录。
2. **拿到提交 SHA**：`git rev-parse HEAD`，得到 40 位十六进制 commit id。
3. **填进索引**：把 `market-index.json` 里 `versions[0].source.commit` 的
   `0000000000000000000000000000000000000000` 换成真实 SHA，`publishTimestamp` 换成
   `date +%s`（Unix 秒）。
4. **提交并推送** `market-index.json`（同一个 commit 里一起更新最省事）。
5. **得到索引地址**（GitHub raw，指向默认分支最新版）：
   `https://raw.githubusercontent.com/Octivy/Agent_Bridge/main/dsh-plugin/market-index.json`

## 三、同事安装（最终体验）

1. 安装 Python 3.11（勾选 Add to PATH）；
2. 打开 DeepSeek Harness → **插件 → 发现 → 添加索引源**，粘贴上面的 raw 地址；
3. 搜索 "agentbridge" → **安装**（确认安装来源为 GitHub）；
4. 运行一次 `runtime\setup.ps1` 安装 Python 依赖（或在插件详情页按提示操作）；
5. 在对话里让 Agent 读图/建模即可。

## 四、npm 方式（可选，更适合版本管理）

若希望走 npm 注册表（`npm publish`），需把 `package.json` 的 `name` 从 `@local/agentbridge`
改成可发布的公开名（如 `agentbridge-dsh`），并同步更新：
- `cordis.patch.yml` 里 `!!js` 路径中的 `/node_modules/@local/agentbridge/` → 新包名路径；
- `market-index.json` 里 `plugins[0].name` 与 `versions[0].source` 改为 `{ "type": "npm", "registry": "..." }`。
然后 `npm publish`，索引里对应版本用 npm source。

## 五、验证

- 索引文件用 `dsh-plugin-market-index` 的 `parseMarketIndex` 校验通过后再发布；
- 安装后，插件详情页应显示中文标题"AgentBridge 桥接"、原创图标、中文详情文档；
- Agent 新会话里应能看到 `mcp__hostmcp__*`、`mcp__cadmcp__*`、`mcp__agentbridge__*` 工具。
