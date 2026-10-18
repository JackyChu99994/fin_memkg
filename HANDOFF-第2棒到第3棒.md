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
  GA 内核移植：约百行通用循环 + 9 原子工具 + LLM function calling。

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
