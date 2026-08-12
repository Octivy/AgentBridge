# 跨机器开发工作流

说明补充：本文档保留为跨机器流程参考。当前默认操作入口请优先看 [daily-dev-sop.md](daily-dev-sop.md)。

更新时间：2026-05-25

如果你只想看一页日常 SOP，优先看 [daily-dev-sop.md](daily-dev-sop.md)。

这份文档只保留“家里/单位两端拷贝开发”所需的最小动作，目标是：

1. 不再拷贝整个工作目录里的机器本地垃圾。
2. 不再拷贝失效的 `copilot_backend/.venv`。
3. 到另一台机器后只执行一个恢复命令。
4. 下次接手时只看这一页，不必重新通读整个项目。

## 推荐流程

### 开始新一天开发

如果当天还没有开发日志，直接复制 [development-log-template.md](development-log-template.md) 为当天日志，例如：

```text
docs/development-log-2026-05-26.md
```

这个模板已经把“交接摘要”嵌在日志顶部，所以当天结束时不必再到处拼接上下文。

### 在目标机器一键拉起本地开发环境

解压交接包后，优先执行：

```powershell
.\start-local-dev.ps1
```

这个脚本会按顺序完成：

1. 调用 `restore-local-dev.ps1` 恢复本机依赖、构建并安装插件。
2. 检查本地 `copilot_backend` 是否已健康可用。
3. 如果服务还没起来，则自动新开一个 PowerShell 窗口启动 `uvicorn`。
4. 做一次 `/health` 健康检查。

如果你只想恢复构建，不想启动服务，可执行：

```powershell
.\start-local-dev.ps1 -SkipService
```

### 在当前机器打交接包

在项目根目录执行：

```powershell
.\prepare-handoff.ps1
```

脚本会生成一个类似下面的压缩包：

```text
AgentBridge-handoff-20260525-231126.zip
```

默认不会打包这些内容：

- `bin/`
- `obj/`
- `.vs/`
- `copilot_backend/.venv/`
- `copilot_backend/.env`
- `agentbridge.config.json`
- `.log`、`.pdb`、`.suo`、`.user`

这意味着你传过去的是“源码 + 文档 + 脚本”，而不是“源码 + 另一台机器的本地环境”。

### 结束当天开发

结束开发前执行：

```powershell
.\finish-dev-session.ps1
```

这个脚本会优先保证当天的 handoff 文件和开发日志都存在：

```text
docs/handoff-YYYY-MM-DD.md
docs/development-log-YYYY-MM-DD.md
```

如果系统里有 `code` 命令，它会直接在 VS Code 中打开这两个文件，方便你在结束开发时顺手补齐总结。

如果你只想生成文件，不想自动打开编辑器：

```powershell
.\finish-dev-session.ps1 -NoOpen
```

### 在目标机器恢复本地环境

解压后，在项目根目录执行：

```powershell
.\restore-local-dev.ps1
```

如果只是日常切换机器，优先还是直接用上面的 `start-local-dev.ps1`，这样少一步手工启动服务。

脚本会做这几件事：

1. 自动查找本机可用的 AutoCAD 安装目录。
2. 如果 `copilot_backend/.venv` 不存在，就在本机重建并安装依赖。
3. 用本机 AutoCAD 引用目录构建插件。
4. 执行 `install.ps1` 安装 bundle。

如果本机 AutoCAD 安装在非常规目录，可显式指定：

```powershell
.\restore-local-dev.ps1 -AutoCADInstallDir "D:\Program Files\Autodesk\AutoCAD 2016"
```

### 启动服务

恢复完成后，如果要走代理模式，再单独启动：

```powershell
.\copilot_backend\.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

## 每次切换机器前只记录这 4 件事

建议把下面四项追加到当天开发日志顶部，这样下次只看当天日志即可：

1. 当前做到哪一步。
2. 下一步准备改哪个文件。
3. 当前本机是否已验证通过构建、安装、服务健康检查。
4. 是否存在机器相关差异，比如 AutoCAD 版本、安装目录、bundle 配置。

推荐格式：

```text
当前状态：
- 已完成：
- 未完成：

下一步：
- 

本机验证：
- build:
- install:
- service health:

机器差异：
- AutoCADInstallDir:
- 其他：
```

也可以直接复制 [handoff-template.md](handoff-template.md) 作为当天的最小交接摘要；如果你当天已经在用 [development-log-template.md](development-log-template.md)，那份日志顶部已经带了同样的信息结构。

## 机器本地文件原则

下面这些内容不要靠“项目拷贝”同步：

1. `copilot_backend/.env`
2. `copilot_backend/.venv/`
3. `%APPDATA%\Autodesk\ApplicationPlugins\AgentBridge.bundle\Contents\agentbridge.config.json`

原因很简单：

1. `.env` 是密钥和本机服务配置。
2. `.venv` 会绑定创建它的那台机器上的 Python 路径，跨机器经常直接失效。
3. bundle 里的配置属于 AutoCAD 本机安装态，不是源码态。

## 当前已验证的家里机器事实

截至 2026-05-25，这台家里机器已验证：

1. AutoCAD 安装目录：`D:\Program Files\Autodesk\AutoCAD 2014`
2. 可用 Python：`py -3` -> 3.13.7
3. 可用 .NET SDK：`dotnet` 8.0.420
4. 可正常执行：`dotnet build .\AgentBridge.sln -c Release -p:Platform=x64 -p:AutoCADInstallDir="D:\Program Files\Autodesk\AutoCAD 2014"`
5. `install.ps1` 已支持保留现有 `agentbridge.config.json`
