# -*- coding: utf-8 -*-
"""一键配置环境：检查 Python → 装依赖 → 写 .env → 连 Neo4j → 建约束 → 灌演示数据 → 跑测试。

    python setup_env.py            # 交互式（推荐第一次用）
    python setup_env.py --yes      # 全部用默认/已有值，不提问
    python setup_env.py --check    # 只体检，不改任何东西
    python setup_env.py --skip-deps --skip-seed

给下一棒：跑完这个脚本，`streamlit run app.py` 就能用。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def step(n: int, title: str) -> None:
    print(f"\n[{n}/6] {title}")
    print("-" * 52)


def read_env(path: Path) -> dict:
    data = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                data[k.strip()] = v.strip()
    return data


def write_env(values: dict) -> None:
    text = "\n".join(f"{k}={v}" for k, v in values.items()) + "\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    shown = "******" if secret and default else default
    tip = f" [{shown}]" if default else ""
    val = input(f"{prompt}{tip}: ").strip()
    return val or default


def check_python() -> bool:
    ok = sys.version_info >= (3, 10)
    print(f"Python {sys.version.split()[0]} " + ("✅" if ok else "❌ 需要 3.10+"))
    return ok


def install_deps() -> None:
    print("安装依赖（约 1-3 分钟）…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
                       cwd=ROOT)
    print("依赖安装 " + ("✅" if r.returncode == 0 else "❌ 失败，请检查网络或代理"))


def check_imports() -> bool:
    mods = ["pandas", "numpy", "streamlit", "pyvis", "neo4j", "openai"]
    missing = []
    for m in mods:
        try:
            __import__(m)
        except Exception:
            missing.append(m)
    if missing:
        print("缺少模块：" + ", ".join(missing))
        return False
    print("核心依赖 ✅")
    return True


def test_neo4j(uri: str, user: str, pwd: str, db: str) -> bool:
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        driver.verify_connectivity()
        with driver.session(database=db or None) as s:
            s.run("RETURN 1").single()
        driver.close()
        print("Neo4j 连接 ✅")
        return True
    except Exception as exc:
        print(f"Neo4j 连接 ❌ {str(exc)[:160]}")
        return False


def seed_demo() -> None:
    import demo_data
    from store import get_store

    store = get_store()
    demo_data.seed(store, reset=True)
    s = store.stats()
    print(f"演示图谱已写入（{store.mode}）：节点 {s['nodes']} · 边 {s['edges']}")


def run_tests() -> None:
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT)
    print("测试 " + ("✅ 全部通过" if r.returncode == 0 else "❌ 有失败，先别急着演示"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--skip-deps", action="store_true")
    ap.add_argument("--skip-seed", action="store_true")
    args = ap.parse_args()

    print("=" * 52)
    print("  Fin-MemKG 环境初始化")
    print("=" * 52)

    step(1, "检查 Python")
    if not check_python():
        sys.exit(1)

    step(2, "安装依赖")
    if args.check:
        check_imports()
        print("\n体检完成（--check 不改任何文件）。")
        sys.exit(0)
    if args.skip_deps:
        print("跳过（--skip-deps）")
    else:
        install_deps()
    if not check_imports():
        print("提示：依赖没装好，后面的步骤会失败。")

    step(3, "配置 .env")
    env = read_env(ENV_PATH)
    if ENV_PATH.exists():
        print(f"已存在 .env（{len(env)} 项），保留原值，只补缺失项。")

    defaults = {
        "DEEPSEEK_BASE_URL": env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "DEEPSEEK_MODEL": env.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "MEMKG_STORE": env.get("MEMKG_STORE", "auto"),
        "MEMKG_BENCHMARK": env.get("MEMKG_BENCHMARK", "000300"),
    }
    if args.yes:
        values = {**defaults, **env}
    else:
        print("直接回车 = 用方括号里的默认值")
        values = {
            "DEEPSEEK_API_KEY": ask("DeepSeek API Key", env.get("DEEPSEEK_API_KEY", ""), secret=True),
            "DEEPSEEK_BASE_URL": defaults["DEEPSEEK_BASE_URL"],
            "DEEPSEEK_MODEL": defaults["DEEPSEEK_MODEL"],
            "NEO4J_URI": ask("Neo4j URI", env.get("NEO4J_URI", "neo4j+s://xxxx.databases.neo4j.io")),
            "NEO4J_USER": ask("Neo4j 用户名", env.get("NEO4J_USER", "")),
            "NEO4J_PASSWORD": ask("Neo4j 密码", env.get("NEO4J_PASSWORD", ""), secret=True),
            "NEO4J_DATABASE": ask("Neo4j 数据库名", env.get("NEO4J_DATABASE", "")),
            "MEMKG_STORE": defaults["MEMKG_STORE"],
            "MEMKG_BENCHMARK": defaults["MEMKG_BENCHMARK"],
        }
    write_env(values)
    print(f"已写入 {ENV_PATH.name}（不会进 git）")

    step(4, "连接 Neo4j")
    ok = test_neo4j(values["NEO4J_URI"], values["NEO4J_USER"],
                    values["NEO4J_PASSWORD"], values["NEO4J_DATABASE"])
    if not ok:
        print("先修好连接再继续；也可以把 MEMKG_STORE 改成 local 先用本地 JSON 演示。")

    step(5, "建约束 + 灌演示数据")
    if args.skip_seed or not ok:
        print("跳过")
    else:
        try:
            seed_demo()
        except Exception as exc:
            print(f"写入失败：{exc}")

    step(6, "跑测试")
    run_tests()

    print("\n" + "=" * 52)
    print("完成。下一步：")
    print("  streamlit run app.py")
    print("  浏览器打开 http://localhost:8501")
    print("提示：答辩前先点一遍 A/B/C 三个场景，确认反转正常。")
    print("=" * 52)


if __name__ == "__main__":
    main()
