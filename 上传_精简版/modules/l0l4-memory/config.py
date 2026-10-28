# -*- coding: utf-8 -*-
"""全局配置：唯一真源（single source of truth）。

所有模块只从这里取路径、常量、凭据，避免 demo_graph.py / update_logic.py
那种“每个文件各写一份配置”的漂移问题。
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEMORY_DIR = ROOT / "memory"
ARCHIVE_DIR = MEMORY_DIR / "L4_archive"
L1_INDEX_PATH = MEMORY_DIR / "L1_concept_index.json"
# 允许实验用独立的 L4 文件（不污染演示归档）
NEWS_JSONL = Path(os.environ.get("MEMKG_L4", str(ARCHIVE_DIR / "news.jsonl")))
LOCAL_GRAPH = ROOT / "data" / "local_graph.json"
PRICE_CACHE = ROOT / "data" / "prices"

for _d in (MEMORY_DIR, ARCHIVE_DIR, PRICE_CACHE):
    _d.mkdir(parents=True, exist_ok=True)


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """极简 .env 读取，不引入 python-dotenv 依赖。已有的环境变量优先。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

# ---------- 凭据 ----------
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# auto: 有 Neo4j 配置就连 Aura，否则退到本地 JSON（答辩现场断网也能演示）
STORE_MODE = os.getenv("MEMKG_STORE", "auto").lower()

# ---------- L0 本体白名单（代码级硬约束，Prompt 只是第一道闸） ----------
ENTITY_TYPES = ("公司", "行业", "产品", "事件")
REL_TYPES = ("利好事件", "利空事件", "供应商", "客户", "竞争对手", "属于行业")
STATUS_ACTIVE = "发酵中"
STATUS_INVALID = "已被证伪"
STATUS_CONFIRMED = "已兑现"
STATUSES = (STATUS_ACTIVE, STATUS_INVALID, STATUS_CONFIRMED)
POLARITY = {"利好事件": 1, "利空事件": -1}
REL_COLOR = {"利好事件": "#e5484d", "利空事件": "#30a46c"}
COLOR_INVALID = "#8b8b8b"
NODE_COLOR = {"公司": "#4c8dff", "行业": "#f5a524", "产品": "#9b6dff", "事件": "#00b8a9"}

# ---------- L3 事件研究 ----------
BENCHMARK_INDEX = os.getenv("MEMKG_BENCHMARK", "000300")  # 沪深 300
EVENT_WINDOW = (-1, 5)      # 事件窗口 [t-1, t+5]
ESTIMATION_WINDOW = 120     # 估计窗口长度（事件前 120 个交易日）

# ---------- UI ----------
APP_TITLE = "Fin-MemKG · 股票量化情报工作台（L0–L4 分层记忆）"


def has_llm() -> bool:
    return bool(DEEPSEEK_API_KEY)


def has_neo4j() -> bool:
    return bool(NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD)
