# 行情数据层交接

工作目录为内层 `fin_memkg`，开发分支 `feat/stage3-market-data`。本次按阶段成果交付，完成内容和剩余限制见 [阶段提交说明](STAGE_DELIVERY.md)；本文记录提交前验收结果，发布状态以 Git 记录为准。

## 1. 交付范围与当前边界

本次提供日线快照可靠性修复、30 分钟缓存与信号检测、细分行业采集与时间约束、字段核验、task_01 / task_36 验收，以及对应的网页查看和运行入口。通用 Agent 联调、KG 接入和完整 40 题系统评测属于后续工作。

- 日线、股票池、399006 指数已经存在；新构建采用 `CURRENT.json` 指向完整版本，下载或写盘失败不会替换上一份可用快照。
- 历史查询过滤基准日之后上市的股票；不包含已退市股票，仍有幸存者偏差。
- 行情使用采集时版本的前复权数据；扩大区间时整段重取单股数据，不拼接不同复权版本。此策略不等于拥有历史时点的复权因子档案。
- 分钟线实现了真实来源适配、缓存、导入和严格覆盖检查；本机新浪/腾讯探测不能提供 task_36 对应的 2024 年区间。该题验收使用官方允许的 `DAILY_OHLC_APPROX`，不能宣传为完成了历史分钟数据覆盖。
- 行业是注明观察时间的当前分类；历史查询默认拒绝把当前分类当作过去事实。
- 流通市值只有在不复权价格、股本生效日期和信息可用日期齐备时才生成准确字段。缺少证据时返回缺失状态。
- 真实数字见 [验收摘要](stage3/acceptance.json)。原始行情、源响应及逐股证据在本地 `data/market/`，不进入 Git。

本次随代码保留的轻量证据包括 [task_01 输出](stage3/task01_codes.txt)、[task_36 输出](stage3/task36_signals.txt)及 [回归日志](stage3/regression.txt)。摘要记录输入报告与运行代码的 SHA-256，便于后续核对；修改代码或更新数据后应重新运行验收，不能沿用旧数字。

## 2. 固定题目版本与计算口径

官方任务文件固定在提交 `3491965a26bd25798677f89cddfa0f12dc01ce32`，SHA-256 为 `f6671317c619e141c84fe65f48b98443ccb67677bac34592be9d1d24eb0a30d1`。下载器保存到忽略目录，评分前校验哈希。只有已检查过的 task_01 和 task_36 评分函数可执行。

来源：[固定版本官方任务](https://github.com/JinyiHan99/GA-Technical-Report/blob/3491965a26bd25798677f89cddfa0f12dc01ce32/datasets/realfin_benchmark/tasks_finance.jsonl)。

| 任务 | 数据与日期 | 本次采用的口径 | 验收 |
|---|---|---|---|
| task_01 | 截至 2026-03-31；信号窗口 03-04～03-31；300 开头且已上市股票 | 每股最多 120 根历史预热；MACD(12,26,9)；Wilder RSI14；窗口内超卖周期首次恢复上穿 50；此前五根成交量均值不含当日；RSI、放量、MA5 上穿 MA8 同日成立；另外保留窗口内 MACD 金叉和至少两次放量要求 | `result.txt`，最多十只；300 秒 |
| task_36 | 截至 2024-08-22，最近五个指数交易日 | 有完整分钟缓存时检测真实 30 分钟急拉/V 型；否则使用明确标注的日线近似；次日验证只读取截止日已知数据，末日保持待验证 | `intraday_signal.txt`；480 秒 |

task_01 原题 prompt 与 expected_behavior 不完全一致。本次使用两者条件的交集，不再为了接近参考名单改用 RSI6。RSI 周期须在信号窗口内出现 <30；初始平盘 RSI 定为 50，单边上涨为 100，单边下跌为 0。排序采用放量天数降序、股票代码升序。独立标量实现复核全部候选，不调用主脚本的指标函数。

task_36 的日线近似采用参考示例中可解释的日振幅、下影线、历史五日均量和收盘位置规则。它不能证明 30 分钟涨跌幅、日内五倍量或两根 K 线反转真实发生。结果保留候选、确认、待验证与否决数量。

自动评分的均值只表示官方自动检查结果。两题均有 hybrid 的 LLM 评分权重，本次未调用评审模型，`overall_score` 保持 null；不把自动检查通过写成完整评测满分。

## 3. 文件与接口

| 文件 | 作用 |
|---|---|
| `market_snapshot.py` | 日线构建、覆盖元数据、原子发布、历史股票池过滤、限时补采 |
| `market_intraday.py` | 新浪/腾讯分钟适配、原始数据导入、分钟与日线近似信号 |
| `market_sectors.py` | 申万分类获取、覆盖统计、当前分类的历史使用约束 |
| `market_fields.py` | 不复权价格与可知历史股本的流通市值计算 |
| `scripts/realfin_contract.py` | 固定版本任务下载与官方自动评分 |
| `scripts/validate_task01.py` / `validate_task36.py` | 两题离线验收与真实过程记录 |
| `scripts/audit_stage3.py` | 快照完整性与独立 task_01 复算 |
| `scripts/validate_fields.py` | 换手率单位、源实现及可选真实样本核验 |
| `scripts/check_stage3.py` | 在隔离副本运行全量回归，避免模拟结果污染演示缓存 |
| `stage3_ui.py` / `stage3_data_ui.py` | 网页入口、日线与指数缓存浏览、行业查询和下载 |
| `stage3_results_ui.py` / `stage3_jobs.py` | 网页验收、独立运行记录、自动检查与结果下载 |

```python
from market_snapshot import load_bars, load_panel, load_universe, load_index, get_bars

bars = load_bars("2026-03-31", codes=["300531"], start_date="2026-01-01")
panel = load_panel("2026-03-31", lookback=60, field="close")
universe = load_universe("2026-03-31")
index = load_index("2026-03-31", lookback=60)

# 默认离线；显式开启后仅少量股票补采，共用等待预算。
subset = get_bars(["300531"], "2026-03-31", "2026-01-01",
                  allow_fetch=False, timeout=5, max_fetch_codes=5)
print(subset.attrs["coverage"])
```

- 日线股票代码接受六位代码以及交易所前后缀，输出统一六位字符串。
- `None` 表示基准日股票池，空列表表示不选择股票。
- `load_panel` 的窗口为最近 N 个市场日期；task_01 单独使用每股最近 N 根可得日线。
- `get_bars` 的 complete 表示源曾成功查询对应区间，不保证每个交易日都有成交；实际首末日期和缺失仍须检查。
- `load_*` 从当前已发布版本读取。直接读取根目录旧 `bars.parquet` 可能得到上一个版本，应使用 `snapshot_paths()` 获取完整版本路径。
- 当前清单源支持创业板和明确标注的深圳主板。沪市主板、科创板不会被错误宣传为已经支持。

## 4. PowerShell 复现命令

在项目目录执行。已有虚拟环境和快照时，无需重新克隆或重新全量下载。

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 首次只读下载固定版题目；之后验收不联网。
.\.venv\Scripts\python.exe scripts/realfin_contract.py --fetch

# 已有快照时按区间复用。要补更早历史，修改 start；要更新，修改 end。
.\.venv\Scripts\python.exe market_snapshot.py build --start 2024-01-01 --end 2026-10-21 --workers 6

# 在线小样本分钟源探测，随后使用保存的证据。
.\.venv\Scripts\python.exe scripts/probe_intraday.py

# 在线获取申万官方批量行业文件；已有下载会直接复用。
.\.venv\Scripts\python.exe market_sectors.py --level 3 --timeout 15

# 离线验收。
.\.venv\Scripts\python.exe scripts/validate_task01.py
.\.venv\Scripts\python.exe scripts/validate_task36.py
.\.venv\Scripts\python.exe scripts/audit_stage3.py
.\.venv\Scripts\python.exe scripts/validate_fields.py --as-of 2026-03-31
.\.venv\Scripts\python.exe scripts/check_stage3.py
```

构建属于事前准备，不能拿构建耗时当作单题运行耗时。默认验收输出分别在 `data/market/acceptance/task01/` 和 `task36/`。

需要真实分钟模式时使用 `scripts/validate_task36.py --mode minute`；覆盖不足会明确失败。`auto` 才允许转为日线近似。有其他来源的合法历史分钟文件时，可用 `market_intraday.py` 的导入命令保存来源和单位，再运行严格覆盖验收。

行业默认使用申万官方[股票分类历史表](https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls)和[分类字典](https://www.swsresearch.com/swindex/pdf/SwClass2021/SwClass.rar)。本机将当前 1411 只股票全部映射至三级分类，并保留一级、二级名称。官方历史文件的更新日期不能替代公告可知日期，默认仍不将今天取得的分类直接用于历史分析。

Windows 使用系统 PowerShell 的 HTTPS 证书链验证以及系统 `tar` 只读提取指定字典成员，不关闭 TLS 校验。其他平台需要支持该 RAR 的 `tar`；不足时应先补齐解包工具。乐咕仅作为显式备用源，批量请求遇到限流时保存失败清单，不以推断标签填满覆盖率。

需要复核来源样本时，可执行以下显式联网命令；默认字段审计只读本地：

```powershell
.\.venv\Scripts\python.exe scripts/validate_fields.py --as-of 2026-10-20 --sample-codes 300001 300750 --direct --timeout 20
```

`--direct` 仅在该次请求中不使用环境代理，不改变系统代理配置，也不关闭证书验证。

## 5. 字段与时间说明

| 字段 | 单位/含义 | 限制 |
|---|---|---|
| 日线 open/high/low/close | 元/股，前复权 | 采集时版本，不是逐时点版本 |
| volume | 股 | 腾讯分钟原始“手”在适配时乘 100 |
| amount | 元 | 不使用价格复权因子调整成交金额 |
| turnover_pct | 百分点，1 表示 1% | 新浪历史流通股本序列重建，来源可修订 |
| float_shares | 股 | 股票清单字段是当前快照，不当作历史股本 |
| float_market_cap | 元 | 必须不复权价 × 当时生效且已知流通股本 |
| 分钟 timestamp | 上海时区、K 线结束时间 | 仅已闭合时段，覆盖缺口不默认为停牌 |
| 行业 available_at | 分类在本系统可获得的时间 | 来源显示纳入日期不等于完整历史归属证据 |

针对行业、股本、复权和退市股票，单纯过滤行情日期不能消除全部前视偏差。对于期后结果，使用独立标签并记录可知日期；不将其混入分析输入。

## 6. 后续协作与提交

第四、五棒使用上述接口，不在每道题现场重新抓取全市场。第六棒可复用真实过程记录，但需要自行完成完整 40 题运行和 LLM judge，不能外推两题结果。

更多题目还涉及其他指数、PE、资金流、ETF 成分、利率、商品以及更长历史。已在 [需求与范围表](STAGE3_REQUIREMENTS.md) 登记，不声称日线缓存已覆盖任意题目。

提交范围为代码、测试、文档和小型验收摘要。`data/market/`、`.venv/`、`.env`、模拟缓存与临时回归副本继续忽略。接收方需按本文准备本地数据后复现验收。

## 7. 网页使用

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

打开 `http://127.0.0.1:8501`，左侧选择“行情数据与验收”。“金融事件与图谱”保留原工作台。

网页接入的验证结果单独保存在 [网页验收摘要](stage3/frontend_acceptance.json) 和 [回归日志](stage3/frontend_regression.txt)：113 项测试通过，浏览器实际运行了两道题及严格分钟失败路径，并核对了四种下载内容。本页依赖已验证的 Streamlit 1.66.0 或更新版本，见 `requirements.txt`。

- **行情缓存**：查看当前快照覆盖、按基准日和股票查看价格/成交量、下载查询结果。日期筛选不触发联网补采。
- **行业映射**：查看当前申万三级分类覆盖与分布，筛选并下载股票分类。历史基准日若早于分类观察时间，严格查询会拒绝；只有明确勾选当前分类对比后才显示带有说明的数据。
- **任务验收**：选择 task_01 或 task_36 后点击运行，查看耗时、自动检查、结果文件和明细。任务基准日固定为官方题目日期，不跟随行情浏览日期改变。task_36 的“严格分钟”模式覆盖不足时失败，“自动”模式允许明确标注的日线近似。

每次网页运行单独写入 `data/market/web_runs/`，保留结果、状态和日志，不覆盖命令行验收目录 `data/market/acceptance/`。刷新或切换标签不会自动重新运行验收。历史运行和下载内容属于对应运行，不代表此后更新的数据或代码已重新验收；网页默认也可查看已有命令行验收。

网页不调用评审模型；自动检查全通过仍不等同于完整 hybrid 评分。缺少本地行情或固定版本任务文件时会提示先完成数据准备。
