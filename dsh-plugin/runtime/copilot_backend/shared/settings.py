import os

from dotenv import load_dotenv


load_dotenv()


MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
CADCOPILOT_OFFICIAL_BASE_URL = os.getenv("CADCOPILOT_OFFICIAL_BASE_URL", MINIMAX_BASE_URL)
CADCOPILOT_OFFICIAL_API_KEY = os.getenv("CADCOPILOT_OFFICIAL_API_KEY", "")
CADCOPILOT_OFFICIAL_MODEL = os.getenv("CADCOPILOT_OFFICIAL_MODEL", MINIMAX_MODEL)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
SERVICE_TIMEOUT_SECONDS = float(os.getenv("SERVICE_TIMEOUT_SECONDS", "90"))
CADCOPILOT_LOCAL_BRIDGE_URL = os.getenv("CADCOPILOT_LOCAL_BRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")
CADCOPILOT_LOCAL_BRIDGE_TOKEN = os.getenv("CADCOPILOT_LOCAL_BRIDGE_TOKEN", "").strip()
CADCOPILOT_LOCAL_BRIDGE_TIMEOUT_SECONDS = float(os.getenv("CADCOPILOT_LOCAL_BRIDGE_TIMEOUT_SECONDS", "30"))
CADCOPILOT_PLANNER_STORE_PATH = os.getenv("CADCOPILOT_PLANNER_STORE_PATH", "").strip()
CADCOPILOT_SKILL_DRAFT_STORE_PATH = os.path.expanduser(
    os.getenv("CADCOPILOT_SKILL_DRAFT_STORE_PATH", "~/.cadcopilot/skill-drafts.json").strip()
)
CADCOPILOT_KNOWLEDGE_ROOTS = os.getenv("CADCOPILOT_KNOWLEDGE_ROOTS", "").strip()
CADCOPILOT_KNOWLEDGE_MAX_FILE_BYTES = int(os.getenv("CADCOPILOT_KNOWLEDGE_MAX_FILE_BYTES", "2097152"))
CADCOPILOT_KNOWLEDGE_MAX_CONTEXT_CHARS = int(os.getenv("CADCOPILOT_KNOWLEDGE_MAX_CONTEXT_CHARS", "6000"))
CADCOPILOT_MODEL_CONFIG_PATH = os.getenv("CADCOPILOT_MODEL_CONFIG_PATH", "").strip()
CADCOPILOT_ADMIN_TOKEN = os.getenv("CADCOPILOT_ADMIN_TOKEN", "").strip()
CADCOPILOT_ADMIN_USERNAME = os.getenv("CADCOPILOT_ADMIN_USERNAME", "admin").strip() or "admin"
CADCOPILOT_ADMIN_PASSWORD = os.getenv("CADCOPILOT_ADMIN_PASSWORD", "cadcopilot-admin").strip() or "cadcopilot-admin"
CADCOPILOT_RELEASE_VERSION = os.getenv("CADCOPILOT_RELEASE_VERSION", "0.2.0").strip() or "0.2.0"
CADCOPILOT_SCHEMA_VERSION = os.getenv("CADCOPILOT_SCHEMA_VERSION", "2.0").strip() or "2.0"


AGENT_SYSTEM_PROMPT = """你是 AgentBridge Planner 的模型连接层。
只能根据请求中提供的 available_tools 和 available_skills 生成结构化决策。
不要直接生成 AutoCAD commands，不要调用未注册工具，不要声称已经修改图纸。
写操作必须先请求 dry-run 预览，并等待本地用户确认。"""


CHAT_SYSTEM_PROMPT = """你是 AgentBridge 的标准模式助手。

规则：
1. 当前模式是标准模式，不要输出任务规划，不要假装调用工具。
2. 直接回答用户问题，必要时给出 CAD 操作建议。
3. 如果用户信息不足，直接指出缺少什么，不要编造。"""
