Fin-MemKG × GenericAgent 复刻 · 交接文档（第 2 棒 → 第 3 棒）
交接日期：2026-10-18
上游仓库：https://github.com/JackyChu99994/fin_memkg （远端仅 1 个提交 5cbf436，2026-10-17，作者 JackyChu）
老师项目：https://github.com/lsdefine/GenericAgent （MIT，Copyright (c) 2025 lsdefine）
官方评测仓库：https://github.com/JinyiHan99/GA-Technical-Report

═══════════════════════════════════════════
0. 一句话背景
═══════════════════════════════════════════
课程选题五（股票量化情报）已确定**按老师项目 GenericAgent 复刻**。
既定技术路线（已拍板，勿再讨论方向）：
  GA 的通用 Agent 内核（约百行循环 + 9 原子工具 + 技能自进化）
  + 我们自有的金融知识图谱挂在 L2/L3 作为记忆层
  + 用官方 RealFin 40 题做客观评测。
理由：课程硬性要求知识图谱，而 GA 本身没有 KG；纯复刻 GA 会丢掉选题五的核心要求。

═══════════════════════════════════════════
1. 六人分工与当前完成度
═══════════════════════════════════════════

第 1 棒（JackyChu）· 已完成并已推送
  基线快照 5cbf436：3,874 行 Python。
  已实现 L0–L4 分层记忆目录（命名与 GA 一致）、个股多空论点图谱
  （ThesisNode：BULLISH/BEARISH × ACTIVE/PRICED_IN/INVALIDATED，强制 evidence_pointers
  与 invalidation_condition）、两跳三节点产业链传导（sector_chains.json + networkx
  确定性计算）、量价诊断 verify_priced_in、L4 证据溯源、时间隔离（as_of_date）、
  Streamlit Demo + Qwen 接入 + 缓存 + 失败不降级、自建评测（30 合成 + 12 真实事件、
  8 种方法/消融对照）、11 项 pytest。

第 2 棒（本次交接人）· 工作已完成，但**尚未提交、尚未推送**
  见下方第 2 节明细。⚠ 这是当前最大风险：所有成果只存在于本机
  D:/cs336/fin_memkg-review 与 D:/cs336/genericagent-ref，远端看不到。

第 3 棒 · 待开始（最高优先级，卡住则全盘卡住）
  本地行情快照层。详见第 4 节。

第 4 棒 · 待开始
  原计划是移植 GA 内核；**第 2 棒已提前完成核心框架**（ga_core/，23 项测试通过）。
  第 4 棒现在负责：真实模型联调（Qwen function calling）、流式输出、
  并行工具调用、真实浏览器桥（TMWebDriver）接入。

第 5 棒 · 待开始
  KG 作为记忆层接入 + 自我进化（任务完成后把执行路径固化成 Skill 写入 L3）。
  这一环 GA 有、我们完全没有，是复刻的核心卖点。

第 6 棒 · 待开始
  RealFin 40 题评测 + 「有 KG vs 无 KG」对照实验 + 技术报告（≥5000 字）、
  期中/期末 PPT、数据集与 demo 代码打包、人员分工与组内互评。
  ⚠ 目前仓库里这些交付物一个都没有。

═══════════════════════════════════════════
2. 第 2 棒实际完成的工作（逐项可复核）
═══════════════════════════════════════════

A. 环境（本机已跑通，可复现）
   - 建 D:/cs336/fin_memkg-review/.venv，Python 3.13.9，requirements.txt 全装完。
     注意：PyPI 直连仅约 20 KB/s 会超时，必须用清华镜像
     -i https://pypi.tuna.tsinghua.edu.cn/simple
   - 11 项 pytest 全过；Streamlit 正常启动（http://localhost:8501）；
     演示模式可出结果；无 Key 时不联网且明确报错（scripts/check_api.py 退出码 1）。

B. 两个真实 Bug 修复（已改，未提交）
   - tools.py：fetch_market_data 的行情获取改为「东方财富 → 新浪 → 腾讯」三级回退；
     并修掉「新闻接口失败会连累行情一起降级为合成数据」的问题。
     现在只拿到行情、新闻失败时仍标记 REAL_MARKET_API，fallback_reason 写 market_source=xxx。
     实测：000002.SZ @2026-10-14 取到 60 根日线 + 9 条新闻，1.31 秒。
   - requirements.txt：pandas 锁 >=2.1.0,<3.0。
     根因实测：pandas 3.0 的 pyarrow 字符串后端不支持 \u3000 正则，
     导致 akshare 的 stock_news_em 抛 ArrowInvalid: Invalid escape sequence: \u。

C. 数据源可行性实测（这决定第 3 棒怎么做，务必先读）
   ❌ 东方财富全废，两条路都不通：
      - 走系统代理（实测 proxies = http://127.0.0.1:7897）→ ProxyError
        （host 82.push2.eastmoney.com / 80.push2.eastmoney.com）
      - NO_PROXY=* 绕过代理 → ConnectionError: Remote end closed connection
      → stock_zh_a_spot_em（全市场快照）、index_zh_a_hist（指数历史）均不可用
   ✅ 可用替代（均已实测）：
      - ak.stock_info_sz_name_code(symbol='A股列表')：SZSE 官方清单，2,906 行 / 1.27 秒，
        板块分布 主板 1495、创业板 1411
      - ak.stock_zh_a_daily（新浪）：0.75 秒/只
      - ak.stock_zh_a_hist_tx（腾讯）：可用
      - ak.stock_news_em（东财新闻）：可用，但前提 pandas<3
   ⚠ 由此推出硬性工程约束（第 3 棒的存在理由）：
      RealFin 任务要在创业板 1411 只上算指标；串行 1411 × 0.75s ≈ 17.6 分钟，
      而任务超时只有 180–600 秒（3–10 分钟）。
      → 必须预建本地行情快照（一次并发下载 + 落盘复用），不能每题现场抓。
   ⚠ 尚未解决的字段缺口：指数 399006 历史、行业分类、流通市值、换手率
      （新浪日线不含后三者），第 3 棒需另找可用源。

D. 拿到官方金融评测基准（重要产出）
   已下载到 D:/cs336/genericagent-ref/realfin/：
   README.md（8,333 B）+ tasks_finance.jsonl（167,634 B，40 行）
   - 40 题，每题一个独立类别；hybrid 32 题、automated 8 题
   - 超时分布：480s×11、300s×10、360s×6、240s×4、420s×4、600s×4、180s×1
   - 每题给固定基准日 + 计算目标 + 输出文件名，**不指定数据接口**（要 Agent 自己想办法）
   - 评分：automated_checks 是一段 Python，def grade(transcript, workspace_path) -> dict
   ⚠ 两个坑（已逐条核对）：
   1. hybrid 题的 llm_judge_criteria 实测是空数组 []，但 grading_weights 写 automated 0.5 /
      llm_judge 0.5 → LLM 评审维度要我们自己补，别指望数据集给。
   2. reference_ans 来自 agent consensus，有内部矛盾，不能当真值。
      例：task_33_sector_leadership 要求「流通市值 > 50 亿」，参考答案却给
      8.33 / 6.70 / 2.47 / 3.73 亿；RSI 出现 100.00 边界值；
      行业标签（新材料、软件服务、医药生物）也不在题目给定的 6 类里。
      → 评分以 automated_checks 为主，reference_ans 当参考实现，人工抽检为辅。

E. 取得老师项目本地参考副本
   D:/cs336/GenericAgent（稀疏克隆，5.4 MB / 169 文件，**LICENSE 与版权声明已保留**）。
   说明：git clone 全量曾被 Connection reset，整包 tarball 46 MB 在 34 KB/s 下超时，
   最终用 --depth 1 --filter=blob:none --sparse 成功；assets 大素材（24 MB demo/图）跳过，
   只单独补了 sys_prompt.txt、insight_fixed_structure.txt、
   global_mem_insight_template.txt、tools_schema.json。
   分析产物在 D:/cs336/genericagent-ref/：复刻对照分析与接棒任务.txt、tree.json（206 文件清单）。

F. 识别出三处数据可信度问题（必须处理，否则报告会出事）
   1. memory/L4_archive/benchmark_results.json 的 evaluation_mode 是
      "RULE_MECHANISM_SIMULATION"，其中 "Ours: Fin-MemKG" 各项 100.0%。
      这不是真实模型结果，**不能当模型效果写进报告**。
   2. memory/L4_archive/eval_results.csv 共 150 行，inference_mode 全是 HEURISTIC_FALLBACK；
      eval_benchmark.py:656 真实跑模型时才写 LIVE_LLM_BENCHMARK。
   3. 预置缓存有假数据：
      - memory/demo_cache/EV_20261012_01_d9e4__qwen-plus.json：事件是「2026Q4 排产上修」，
        结论却写「2025Q2 800G 增长 35%」，事件与结论不匹配。
      - memory/graph_demo_cache/graph_300308.SZ_2026-10-14_b7d9feb1f4__qwen-plus.json：
        token 是 80/48，正好等于单元测试里的假值。
      → 真实实验前必须清缓存，或取消勾选界面上的「优先使用本地缓存」。

═══════════════════════════════════════════
3. 第 3 棒接手前必须知道的环境事实
═══════════════════════════════════════════
- Windows 下跑中文输出脚本必须设 PYTHONUTF8=1，否则报 GBK 解码错。
- Git Bash 里 /d/、/tmp/ 这种路径 Python 看不见，一律用 D:/ 风格。
- 本机 python 命令是应用商店占位符（退出码 49），真解释器是 /d/anaconda/python.exe，
  项目内则用 D:/cs336/fin_memkg-review/.venv/Scripts/python.exe。
- 系统代理 127.0.0.1:7897 会拦东方财富域名；github.com 网页与 git 全量克隆不稳，
  api.github.com 稳定（匿名只读 60 次/小时/IP）。
- GenericAgent 要求 Python 3.11/3.12，**不要 3.14**；现有 .venv 是 3.13.9。
  → 第 4 棒移植 GA 内核时要另建 3.12 环境，不要和 fin_memkg 的 3.13 混用。

═══════════════════════════════════════════
4. 第 3 棒的任务：本地行情快照层（P1，最高优先级）
═══════════════════════════════════════════
目标：让 RealFin 任意一题能在其超时（180–600 秒）内拿到所需行情，而不是现场抓 1411 只。

建议做法（供参考，可自行调整）：
1. 用 SZSE 官方清单取创业板 1411 只代码（1.27 秒，已验证可用）。
2. 并发从新浪 stock_zh_a_daily 下载日线，落盘为本地数据集；
   按「基准日可切」的方式组织，保证 timestamp <= as_of_date，杜绝前视偏差
   （这是 L0 元规则第 1 条，也是 .cursorrules 第 2 条的硬约束）。
3. 补齐字段缺口：指数 399006 历史（东财不通，需找新浪/腾讯替代）、
   行业分类、流通市值、换手率。
4. 提供统一读取接口给上层：给 (股票池, 基准日, 回看窗口) 就返回 DataFrame，
   内部自动走缓存、缓存未命中才联网。
5. 验收标准：task_01_macd_rsi_filter（基准日 2026-03-31，创业板 MACD 金叉 +
   RSI 从 <30 反弹到 >50 + 成交量至少 2 天超 5 日均量 2 倍 + 5 日均线上穿 8 日均线）
   能在 300 秒超时内产出 result.txt，且用官方 automated_checks 打出分。

═══════════════════════════════════════════
5. 合规提醒
═══════════════════════════════════════════
- GenericAgent 是 MIT：复制其代码必须保留 LICENSE 与版权声明，我们仓库里也要放一份。
- 复刻不等于抄报告：GA 的评测数字是他们在 Claude/GPT/MiniMax 上的结果，
  不能搬到我们报告里当自己的成绩。
- 金融数据与新闻抓取注意来源条款；对外发布数据集前去掉不必要的个人信息。
- 本报告严禁出现未经真实运行得到的数字（第 2 节 F 那三处就是反例）。

═══════════════════════════════════════════
6. P1 已落地：本地行情快照层（第 2 棒交付）
═══════════════════════════════════════════

新增文件：
- market_snapshot.py
  - build：并发下载创业板日线（新浪源，qfq 复权）并落盘 parquet
  - sectors：给股票池补新浪行业字段
  - load_bars / load_panel / load_universe / load_index：统一读取，
    严格按 date <= as_of_date 切片，杜绝前视偏差
- scripts/validate_task01.py：task_01 端到端验收脚本
- .gitignore 增加 data/market/（生成数据不入库）
- requirements.txt 增加 pyarrow>=14.0.0

生成数据（不入库，需各组员自行 build）：
  data/market/bars.parquet、universe.parquet、index.parquet、meta.json

实测基准（2026-10-18）：
- 新浪指数 399006：0.21 秒，3,975 根日线，覆盖 2010-06 至今
- 小规模构建：40 只 / 9.3 秒 / 26,901 行 / 零失败（已验证落盘与切片）
- 8 并发下载 24 只：4.5 秒，零失败；理论 1411 只约 4–6 分钟
- **全量实测失败**：跑到 1400/1411 时累计 43 只失败（新浪限流），
  且最后若干请求无响应导致进程挂住 18 分钟未落盘。
  → 第 3 棒必须先补两点再跑全量：
    1. 给每只股票的请求加独立超时（akshare 的 stock_zh_a_daily 不暴露 timeout，
       需用信号/线程池 future.result(timeout=) 或换 requests 直连新浪）；
    2. 每下完 N 只就增量落盘（断点续传），不要等全部完成才写。
  本次已停止该任务；data/market/ 里保留的是 40 只的验证快照。
- 东方财富仍不可用（代理 ProxyError / 绕过则断连），不要再用

⚠ 两个新发现的坑（写报告时必须知道）：
1. **官方 automated_checks 很弱**。以 task_01 为例，它只检查：
   文件是否存在、代码是否为 3 开头 6 位、行数是否 ≤10，
   以及 transcript 里有没有出现 "kline/ohlcv"、"macd"、"rsi"、"ma5/均线" 这些关键词。
   **它完全不校验选股结果正确不正确。**
   而 hybrid 的另一半 LLM 评审维度又是空数组。
   → 如果只看官方分数，会得出"系统很好"的假象。第 6 棒必须自己加正确性指标：
     与 reference_ans 重合度、或独立重算指标复核，否则报告不可信。
2. **task_36_intraday_anomaly 需要 30 分钟 K 线**，日线快照覆盖不了。
   34/40 题明确要求创业板，日线快照可支撑大部分任务；
   这 1 题需要另找分钟级数据源（新浪/腾讯分钟线需单独验证，东财分钟线不可用）。

═══════════════════════════════════════════
7. 第 4 棒（GA 内核移植）的准确规格
═══════════════════════════════════════════
不要凭印象重写，按老师源码对齐（本地 D:/cs336/GenericAgent）：
- 入口：agent_runner_loop(client, system_prompt, user_input, handler, tools_schema, max_turns=40)
- 每轮：client.chat(messages, tools=tools_schema) → 解析 tool_calls →
  handler.dispatch(tool_name, args)（对应 do_<tool_name> 方法）→
  汇总 tool_results → turn_end_callback 生成 next_prompt → 下一轮
- 历史不塞回 messages，由 Session 持有（llmcore.py），每轮只追加一条 user 消息
- 退出条件：should_exit / 无 next_prompt / 达到 max_turns
- 工具结果结构：{"tool_use_id": id, "content": str}
- 每 10 轮清一次 client.last_tools
- 9 个工具定义见 assets/tools_schema.json（已下载到本地）
- Python 用 3.11/3.12；现有 3.13.9 的 .venv 不要复用来跑 GA 内核

═══════════════════════════════════════════
8. GA 核心框架已落地（第 2 棒交付，可直接跑）
═══════════════════════════════════════════

新增 ga_core/ 包（与既有 agent_loop.py 领域管线互不影响）：
- session.py   消息结构，标准 OpenAI function-calling 格式
- llm.py       Qwen / OpenAI 兼容客户端 + FakeClient（测试用）
- loop.py      通用循环 AgentLoop：调模型 → 执行工具 → 回灌结果 → 直到无工具调用
- tools.py     9 个原子工具：code_run、file_read、file_write、file_patch、
               web_scan、web_execute_js、ask_user、
               update_working_checkpoint、start_long_term_update
- handler.py   工具调度（未知工具/异常都会回灌给模型，不静默吞掉）
- memory.py    L0–L4 读取 + 系统提示拼装 + crystallize_skill（写 L3）
- cli.py       命令行入口

验证（2026-10-18）：
- pytest 23 项全过（原 11 项 + 新增 12 项）
- 无 API Key 也能自检：
    python -m ga_core.cli "自检" --fake --max-turns 5
  实际执行了 file_write → file_read → 输出最终答复，三轮结束。

已知边界（第 4 棒继续补）：
- web_execute_js 目前是扩展点，未接真实浏览器（老师用 TMWebDriver）；
  web_scan 只是静态 HTTP 读取，没有登录态。
- 未接入工具的并行调用与流式输出。
- start_long_term_update 只返回提纯指令，真正写记忆由模型用 file_read/file_patch 完成
  （与老师设计一致）。
- .cursorrules 写"总代码 <1000 行"，实际项目已 3,874 行；新框架又增加约 600 行。
  这条规则建议更新，否则与实际长期不符。

运行方式：
    ./.venv/Scripts/python.exe -m ga_core.cli "分析某只股票" --max-turns 20
    ./.venv/Scripts/python.exe -m ga_core.cli "自检" --fake
  系统提示会自动加载 memory/L0_meta_rules.md 与 L1 索引；
  L2 图谱、L3 技能、L4 归档由模型按需 file_read。


