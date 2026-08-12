# 日常开发操作流程

说明：本文档是当前仓库唯一的日常开发操作流程文档。开始开发、结束开发、打包交接、同步 GitHub 时，默认以本文档为准。

更新时间：2026-05-26

这份文档只回答一件事：以后你每天怎么开始开发、怎么结束开发，才能同时满足下面 4 个目标：

1. 单位和家里都能继续开发。
2. 两边切换时只传必要源码，不传机器本地垃圾。
3. 解压后可以快速恢复环境并启动。
4. 家里可以把当天稳定版本推到 GitHub 做归档。

## 核心原则

以后固定分成两套资产：

1. 源码交接资产：项目源码、文档、脚本。
2. 机器本地资产：AutoCAD 安装、bundle 配置、`copilot_backend/.env`、`copilot_backend/.venv`。

不要再把第二类资产跟着源码一起拷来拷去。

## 你以后固定只记 4 个命令

开始开发：

```powershell
.\start-local-dev.ps1
```

结束开发并打开当天总结文件：

```powershell
.\finish-dev-session.ps1
```

打交接包：

```powershell
.\prepare-handoff.ps1
```

家里归档到 GitHub：

```powershell
git status
git add .
git commit -m "..."
git push
```

## 场景 A：到一台机器后，开始当天开发

适用场景：

1. 你刚到单位电脑或家里电脑。
2. 你刚把 handoff zip 解压出来。
3. 你昨天没关机，但想重新确认本机环境可用。

操作顺序：

1. 进入项目根目录。
2. 如果当天还没有日志，从 [development-log-template.md](development-log-template.md) 复制一份当天日志，例如 `docs/development-log-YYYY-MM-DD.md`。
3. 执行：

```powershell
.\start-local-dev.ps1
```

4. 脚本完成后，检查这 3 件事：
   - build 已完成
   - bundle 已安装
   - `http://127.0.0.1:8000/health` 可用
5. 如果 AutoCAD 里功能正常但 MCP / 本地工具桥异常，直接执行：

```powershell
.\diagnose-local-bridge.ps1
```

它会一次性检查 `8000/health`、`8765/health`、bundle 配置、`cadcopilot.log` 里的 `LocalToolBridge` 相关日志，以及 bundle DLL 和最新构建 DLL 是否一致。
6. 打开 AutoCAD 2024，执行 `AICHAT` 或 `AISNAPSHOT` 做一次最小冒烟验证。
7. 在当天日志顶部填写：当前状态、下一步、本机验证、机器差异。

这一步的目标不是“开始写代码”，而是先把本机环境拉回可工作状态。

## 场景 B：单位结束当天开发，准备带回家

适用场景：

1. 单位网络不能稳定连 GitHub。
2. 你准备把今天的改动带回家继续做。

操作顺序：

1. 在项目根目录执行：

```powershell
.\finish-dev-session.ps1
```

2. 这条脚本现在会确保下面两个文件都存在：
   - `docs/handoff-YYYY-MM-DD.md`
   - `docs/development-log-YYYY-MM-DD.md`
3. 补完当天 handoff 和开发日志顶部的交接摘要，至少写清：
   - 已完成
   - 未完成
   - 下一步
   - 本机验证结果
   - 机器差异
4. 执行：

```powershell
.\prepare-handoff.ps1
```

5. 把生成的 handoff zip 拷回家。
6. 不要手工拷这些内容：
   - `bin/`
   - `obj/`
   - `.vs/`
   - `copilot_backend/.venv/`
   - `copilot_backend/.env`
   - `%APPDATA%\Autodesk\ApplicationPlugins\AgentBridge.bundle`

这一步的目标不是“做备份”，而是生成一份干净可恢复的源码交接包。

## 场景 C：回到家里，继续开发

操作顺序：

1. 解压单位带回来的 handoff zip。
2. 进入项目根目录。
3. 先看当天的 `docs/handoff-YYYY-MM-DD.md` 或当天开发日志顶部交接摘要。
4. 执行：

```powershell
.\start-local-dev.ps1
```

5. 打开 AutoCAD 做一次最小验证。
6. 继续当天开发。

这一步的关键是：先读交接摘要，再启动本机环境，不要重新通读整个项目。

## 场景 D：家里结束当天开发，并归档到 GitHub

适用场景：

1. 你在家里网络可以正常访问 GitHub。
2. 你希望把当天稳定版本留档，避免只有 zip 交接，没有历史。

操作顺序：

1. 先执行：

```powershell
.\finish-dev-session.ps1
```

2. 检查当天开发日志和 handoff 摘要是否已补齐。
3. 执行：

```powershell
git status
```

4. 确认没有误带这些本地文件：
   - `copilot_backend/.env`
   - `copilot_backend/.venv/`
   - `bin/`
   - `obj/`
   - 本机日志垃圾
5. 执行：

```powershell
git add .
git commit -m "docs: update handoff and dev state"
git push
```

6. 如果第二天还要去单位继续开发，再顺手执行：

```powershell
.\prepare-handoff.ps1
```

这一步的目标是同时保留两种恢复路径：

1. GitHub 版本历史。
2. 立即可带走的 handoff zip。

## 每天最短可执行闭环

如果你只想记最短版本，就记下面这个：

早上开始：

1. 解压或进入项目目录。
2. 看当天 handoff 摘要。
3. `./start-local-dev.ps1`
4. AutoCAD 冒烟验证。

晚上结束：

1. `./finish-dev-session.ps1`
2. 补 handoff 和当天开发日志摘要。
3. `./prepare-handoff.ps1`
4. 如果在家里并且网络正常，再执行 `git push`。

## 什么时候用 handoff zip，什么时候用 GitHub

优先用 handoff zip：

1. 单位网络无法稳定访问 GitHub。
2. 你只需要把今天的源码带到另一台机器继续做。

优先用 GitHub：

1. 你在家里网络稳定。
2. 你希望保留提交历史。
3. 你希望以后能按提交点回退。

推荐实际策略：

1. 单位到家里：靠 handoff zip。
2. 家里结束开发：推 GitHub 做归档。
3. 第二天单位继续：如果单位网络还是不通，就继续走 handoff zip。

## 失败时先查什么

如果解压后启动不顺，优先检查：

1. 是否执行了 `./start-local-dev.ps1`
2. 本机 AutoCAD 目录是否被正确识别
3. `copilot_backend/.venv` 是否是在当前机器本机重建的
4. `copilot_backend/.env` 是否存在且是本机有效配置
5. bundle 里的 DLL 是否为最新安装版本
6. 直接运行 `./diagnose-local-bridge.ps1`，先看 `8765/health`、`LocalToolBridge listening` 和 DLL 比对结果

如果“代码改了但 CAD 里没变化”，优先查部署链路，不要先怀疑源码本身。
