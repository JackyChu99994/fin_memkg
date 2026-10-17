# Fin-MemKG 金融事件结构化分析 Demo（第一版 · 固定使用 Qwen API）

本项目第一版 Demo 固定使用阿里云 DashScope 提供的 **Qwen OpenAI 兼容 Chat Completions 接口**，完成金融事件的结构化分析演示。

## 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置 Qwen 环境变量

第一版 Demo 仅读取以下三个配置项（读取顺序：**1. 系统环境变量 $\to$ 2. 项目根目录 `.env` 文件**）：

- `QWEN_API_KEY`（必填）
- `QWEN_BASE_URL`（可选，默认：`https://dashscope.aliyuncs.com/compatible-mode/v1`）
- `QWEN_MODEL`（可选，默认：`qwen-plus`）

可在系统环境变量中导出，或写入项目根目录 `/Users/huaijinchu/Desktop/fin_memkg/.env`：

```ini
QWEN_API_KEY=你的_DashScope_API_Key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

> **注意**：当前版本不再读取或推断 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`LLM_*`、`DEEPSEEK_*` 或 `OPENAI_WIRE_API`。

## 3. 启动 Demo

在项目根目录执行：

```bash
.venv/bin/streamlit run app.py
```

页面启动后会默认加载一条项目内置的固定金融事件（启动时不会自动发起任何 API 请求）。

## 4. 如何使用演示模式与调用 Qwen API

页面提供两个操作按钮：

1. **进入演示模式（点击“使用演示结果”按钮）**：
   - 不发起任何网络请求，无需配置 `QWEN_API_KEY`；
   - 直接展示项目内置的固定结构化分析结果，并在页面明确标记 **`“当前为演示数据，未调用 Qwen API”`** 与结果来源 **`“演示数据，未调用 API”`**。
2. **调用 Qwen API（点击“调用 Qwen API”按钮）**：
   - 读取 `QWEN_API_KEY`、`QWEN_BASE_URL`、`QWEN_MODEL`；
   - 若命中本地成功响应缓存，显示 **`“缓存结果，未发送新的 API 请求”`**；
   - 若未命中缓存，使用 OpenAI Python SDK 的 `client.chat.completions.create(...)` 向 Qwen 发送一次请求（关闭自动重试，一次点击最多发送一次请求），成功后显示 **`“Qwen 实时 API 结果”`**。
   - 也可在终端运行单次最小连通性验证命令：
     ```bash
     .venv/bin/python scripts/check_api.py
     ```

## 5. 失败处理与当前版本限制

1. **API 调用失败不会自动降级为真实分析**：当缺少 `QWEN_API_KEY` 或接口返回 HTTP 502、401、403、超时、非合法 JSON 时，页面会清除旧结果并显示简洁提示 **`“Qwen API 调用失败，未生成真实分析结果。”`**（同时列出错误类型、HTTP 状态码、当前模型名称、Base URL 主机名、是否发生过真实请求，并将详细错误收入折叠区），**绝不自动重试，也绝不使用启发式规则或演示数据冒充真实模型分析结果**。
2. **暂不支持原有 Responses API 和其他供应商**：当前版本仅支持 Qwen OpenAI 兼容 Chat Completions 接口，不支持 Responses API、多协议分支或多供应商自动切换。
3. **完整 Benchmark 暂时隐藏**：全量 Benchmark 评测、多方法对比、消融实验与复杂多跳图谱维护入口已从默认流程和界面中暂时隐藏（相关底层代码与数据文件保留在仓库中）。
