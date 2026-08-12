const release = {
  version: "0.9.0.622",
  file: "/downloads/AgentBridge-0.9.0.622-AutoCAD-2024.zip",
  manifest: "/downloads/latest.json",
};

const capabilities = [
  {
    index: "01",
    title: "多模型对话入口",
    text: "在 CAD 内连接 OpenAI、Claude、DeepSeek、MiniMax、Ollama 与企业内网兼容接口。",
    status: "已实现",
  },
  {
    index: "02",
    title: "标准 CADMCP",
    text: "Codex 与其他 MCP Host 可读取图纸快照、图层、实体和功能对象，并调用受控操作。",
    status: "已通过连接验收",
  },
  {
    index: "03",
    title: "规范可信问答",
    text: "先检索授权的本地 Markdown/TXT 资料，再生成带来源编号的回答；无来源时拒答。",
    status: "MVP 可用",
  },
  {
    index: "04",
    title: "安全任务 Agent",
    text: "计划只调用白名单能力；写图经过预览、一次性授权、事务提交与可选回滚。",
    status: "MVP 可用",
  },
  {
    index: "05",
    title: "专业 Skill 容器",
    text: "已包含图纸分析、功能对象识别、外围轮廓和统一图层四类最小 Skill。",
    status: "待真实图纸硬化",
  },
  {
    index: "06",
    title: "任务沉淀为 Skill",
    text: "成功任务可生成待审核 Skill 草稿，校验工具白名单后再由用户决定是否发布。",
    status: "草稿链路已实现",
  },
];

const hostItems = ["Codex", "Claude", "OpenAI", "Ollama", "企业模型"];

function BrandMark() {
  return (
    <svg viewBox="0 0 46 46" aria-hidden="true">
      <path d="M8 7h30v32H8z" className="mark-frame" />
      <path d="M15 31V15h13l4 4v12H15Z" className="mark-shape" />
      <path d="M28 15v5h5M12 12h5M12 34h5M34 12v5M34 29v5" className="mark-lines" />
    </svg>
  );
}

function Blueprint() {
  return (
    <div className="blueprint" aria-label="CAD 图纸与 AI 连接示意">
      <div className="blueprint-toolbar">
        <span>PLAN_01.DWG</span>
        <span className="live-dot">CONNECTED</span>
      </div>
      <svg viewBox="0 0 680 470" role="img" aria-hidden="true">
        <defs>
          <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M24 0H0V24" fill="none" stroke="currentColor" strokeOpacity=".08" />
          </pattern>
        </defs>
        <rect width="680" height="470" fill="url(#grid)" />
        <g className="plan-dim">
          <path d="M84 102H565V377H84Z" />
          <path d="M94 112H555V367H94Z" />
          <path d="M285 112V225M285 278v89M418 112V367" />
          <path d="M94 249H210M260 249H418M418 276H555" />
          <path d="M210 249a50 50 0 0 1 50 50" />
          <path d="M285 225a53 53 0 0 1 53 53" />
          <path d="M418 276a50 50 0 0 1 50-50" />
        </g>
        <g className="plan-highlight">
          <path d="M78 96H571V383H78Z" />
          <circle cx="78" cy="96" r="4" />
          <circle cx="571" cy="96" r="4" />
          <circle cx="571" cy="383" r="4" />
          <circle cx="78" cy="383" r="4" />
        </g>
        <g className="plan-labels">
          <text x="118" y="184">WORKSPACE</text>
          <text x="315" y="184">MEETING</text>
          <text x="455" y="184">STUDIO</text>
          <text x="120" y="322">LOBBY</text>
          <text x="313" y="322">SERVICE</text>
          <text x="457" y="329">CORE</text>
        </g>
        <g className="measure">
          <path d="M78 73H571M78 67v12M571 67v12" />
          <text x="302" y="62">24 600</text>
          <path d="M600 96V383M594 96h12M594 383h12" />
          <text x="615" y="245" transform="rotate(90 615 245)">14 280</text>
        </g>
      </svg>
      <div className="blueprint-result">
        <span>外围轮廓</span>
        <strong>识别完成</strong>
        <span>351.29 m²</span>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <main>
      <nav className="nav shell">
        <a className="brand" href="#top" aria-label="AgentBridge 首页">
          <BrandMark />
          <span>AGENTBRIDGE</span>
          <small>CONNECTOR / 2024</small>
        </a>
        <div className="nav-links">
          <a href="#capabilities">能力</a>
          <a href="#architecture">架构</a>
          <a href="#download">下载</a>
          <a href="#install">安装</a>
        </div>
        <a className="nav-download" href={release.file} download>
          获取插件 <span>↓</span>
        </a>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="pulse" />
            AUTO CAD 2024 · MCP READY
          </div>
          <h1>
            让 AI 读懂图纸，
            <br />
            <em>安全地完成 CAD 任务。</em>
          </h1>
          <p className="hero-lead">
            AgentBridge 是 AutoCAD 与大模型之间的连接器基座。连接 Codex、Claude、本地模型和企业模型，
            通过标准 MCP 读取图纸，并以受控 Skill 执行任务。
          </p>
          <div className="hero-actions">
            <a className="button primary" href={release.file} download>
              <span>下载 AutoCAD 2024 插件</span>
              <b>↓</b>
            </a>
            <a className="button text-button" href="#architecture">
              查看工作方式 <span>↗</span>
            </a>
          </div>
          <div className="hero-meta">
            <div>
              <span>当前版本</span>
              <strong>v{release.version}</strong>
            </div>
            <div>
              <span>适配平台</span>
              <strong>Windows · x64</strong>
            </div>
            <div>
              <span>产品阶段</span>
              <strong>MVP / Preview</strong>
            </div>
          </div>
        </div>
        <Blueprint />
      </section>

      <section className="host-strip">
        <div className="shell host-row">
          <span>一个连接器，接入你的模型与 Agent</span>
          <div className="host-list">
            {hostItems.map((item) => (
              <b key={item}>{item}</b>
            ))}
          </div>
        </div>
      </section>

      <section className="section shell" id="capabilities">
        <div className="section-heading">
          <div>
            <span className="kicker">CAPABILITY MAP</span>
            <h2>连接是基座，Skill 才是能力。</h2>
          </div>
          <p>
            第一版先验证模型能连、图纸能读、任务能安全执行，再用真实 DWG 数据逐步扩展专业能力。
          </p>
        </div>
        <div className="capability-grid">
          {capabilities.map((item) => (
            <article className="capability-card" key={item.index}>
              <div className="card-top">
                <span>{item.index}</span>
                <i>{item.status}</i>
              </div>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
              <div className="card-line" />
            </article>
          ))}
        </div>
      </section>

      <section className="architecture-section" id="architecture">
        <div className="shell">
          <div className="section-heading light">
            <div>
              <span className="kicker">CONTROLLED WORKFLOW</span>
              <h2>每一次写图，都经过明确边界。</h2>
            </div>
            <p>
              模型不直接控制 AutoCAD。CADMCP 将读取、规划、授权、事务和回滚拆成可审计的步骤。
            </p>
          </div>
          <div className="flow">
            <div className="flow-node">
              <span>01</span>
              <strong>用户 / Agent</strong>
              <small>描述任务与验收目标</small>
            </div>
            <i>→</i>
            <div className="flow-node">
              <span>02</span>
              <strong>CADMCP</strong>
              <small>工具白名单与参数校验</small>
            </div>
            <i>→</i>
            <div className="flow-node active">
              <span>03</span>
              <strong>预览与授权</strong>
              <small>一次性许可 / 可拒绝</small>
            </div>
            <i>→</i>
            <div className="flow-node">
              <span>04</span>
              <strong>AutoCAD 事务</strong>
              <small>提交、Handle 校验、回滚</small>
            </div>
          </div>
          <div className="safety-note">
            <span>SAFETY CONTRACT</span>
            <p>
              当前 MCP 对外只保留 13 个产品工具。识别失败会明确返回未知项，未经授权的写入不会执行。
            </p>
          </div>
        </div>
      </section>

      <section className="download-section shell" id="download">
        <div className="download-card">
          <div className="download-copy">
            <span className="kicker">LATEST PREVIEW</span>
            <h2>AgentBridge for AutoCAD 2024</h2>
            <p>
              适用于 Windows x64 与 AutoCAD 2024（R24.3）。压缩包包含插件 Bundle、安装/卸载脚本和使用说明。
            </p>
            <div className="release-tags">
              <span>.NET Framework 4.8</span>
              <span>AutoCAD 2024</span>
              <span>Windows x64</span>
            </div>
          </div>
          <div className="release-panel">
            <div className="release-version">
              <span>VERSION</span>
              <strong>{release.version}</strong>
            </div>
            <div className="release-info">
              <span>渠道</span>
              <b>Preview</b>
              <span>发布日期</span>
              <b>2026.07.27</b>
              <span>完整性</span>
              <b>SHA-256</b>
            </div>
            <a className="button primary full" href={release.file} download>
              下载插件包 <b>↓</b>
            </a>
            <a className="manifest-link" href={release.manifest}>
              查看版本清单与校验值 ↗
            </a>
          </div>
        </div>
        <p className="preview-warning">
          <strong>预览版说明：</strong>
          连接器链路已通过自动化验收；外围轮廓、图层统一等写图 Skill 仍需在更多真实 DWG 上硬化，不建议直接用于无人值守的生产批处理。
        </p>
      </section>

      <section className="install-section" id="install">
        <div className="shell install-grid">
          <div className="install-title">
            <span className="kicker">3-MIN INSTALL</span>
            <h2>解压、安装、重启 AutoCAD。</h2>
            <p>安装器会保留已有配置，并为本地桥自动生成随机访问令牌。</p>
          </div>
          <ol className="steps">
            <li>
              <span>01</span>
              <div>
                <strong>下载并解压插件包</strong>
                <p>不要直接在压缩包内运行脚本。</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>运行 Install-AgentBridge.ps1</strong>
                <p>插件将安装到当前用户的 Autodesk ApplicationPlugins 目录。</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>重启 AutoCAD 2024</strong>
                <p>输入 TESTCOPILOT 检查连接，输入 AICHAT 打开对话面板。</p>
              </div>
            </li>
          </ol>
        </div>
      </section>

      <section className="roadmap shell">
        <div className="roadmap-main">
          <span className="kicker">WHAT&apos;S NEXT</span>
          <h2>从真实图纸验证，走向可复用专业 Skill。</h2>
        </div>
        <div className="roadmap-items">
          <div>
            <span>NOW</span>
            <strong>连接器稳定性</strong>
            <p>真实模型、第二 Host、断线恢复与诊断。</p>
          </div>
          <div>
            <span>NEXT</span>
            <strong>真实 DWG 硬化</strong>
            <p>外围轮廓、统一图层、失败样本回归。</p>
          </div>
          <div>
            <span>LATER</span>
            <strong>企业 Skill 平台</strong>
            <p>审核、签名、版本化和组织内分发。</p>
          </div>
        </div>
      </section>

      <footer>
        <div className="shell footer-row">
          <div className="brand footer-brand">
            <BrandMark />
            <span>AGENTBRIDGE</span>
          </div>
          <p>AI connection layer for AutoCAD · MVP Preview</p>
          <div>
            <a href="#top">返回顶部 ↑</a>
            <a href={release.manifest}>版本清单</a>
          </div>
        </div>
      </footer>
    </main>
  );
}
