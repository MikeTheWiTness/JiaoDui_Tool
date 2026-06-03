"""
符号计算审校 Agent 测试界面

显示 ReAct 循环中每一步的完整日志 + 最终审校报告。
"""
import base64
import json
import os
import sys
import time
import traceback

import streamlit as st

st.set_page_config(page_title="物理审校 Agent 测试", page_icon="🔬", layout="wide")

# ---- 侧边栏 ----
with st.sidebar:
    st.header("API 配置")
    config_path = os.path.join(os.path.dirname(__file__), "api_config.json")
    saved_config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            saved_config = json.load(f)

    api_url = st.text_input(
        "API URL", value=saved_config.get("api_url", ""),
        placeholder="https://ark.cn-beijing.volces.com/api/v3/",
    )
    api_key = st.text_input("API Key", value=saved_config.get("api_key", ""), type="password")
    model_name = st.text_input("Model", value=saved_config.get("model", "doubao-seed-2-0-pro-260215"))
    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.05)
    max_iterations = st.number_input("最大 ReAct 轮数", 1, 20, 5, 1)

    st.divider()
    st.caption("6 工具: evaluate | solve | equality | simplify | physics_formula | dimensional")

# ---- 标题区 ----
st.title("🔬 符号计算审校 Agent 测试")
st.caption("ReAct 循环 · doubao + SymPy 沙箱 · 6 个数学工具")

# ---- 输入区 ----
with st.expander("📝 题目输入", expanded=True):
    col_a, col_b = st.columns([2, 1])
    with col_a:
        problem_text = st.text_area(
            "题目内容（Markdown）",
            value=st.session_state.get("problem_text", """## 第1题
**例1** 一辆汽车从静止开始以恒定加速度运动，经过5秒后速度达到20 m/s。
求：(1) 汽车的加速度；(2) 前5秒内的位移。

**解析** (1) 由 v = v₀ + at，v₀=0, t=5, v=20：
加速度 a = v/t = 20/5 = 4 m/s²

(2) 位移 s = v₀t + ½at² = 0 + ½×4×25 = 50 m

**答案** (1) 4 m/s²; (2) 50 m"""),
            height=260,
        )
    with col_b:
        uploaded_files = st.file_uploader(
            "配图（可选）", type=["png", "jpg", "jpeg"], accept_multiple_files=True,
        )

        st.divider()
        st.caption("快速加载预设题目：")
        quick = {
            "匀加速运动": """## 第1题
一辆汽车从静止开始以加速度a=4m/s²运动，经过5秒。
求：(1) 末速度；(2) 位移。
**答案** (1) 20 m/s; (2) 50 m""",
            "竖直上抛": """## 第2题
质量为2 kg的物体从地面以10 m/s初速度竖直上抛。
求最高点的机械能。(g=10 m/s²)
**答案** 100 J""",
            "欧姆定律": """## 第3题
电阻10Ω的导体两端加220V电压。
求：(1) 电流；(2) 电功率。
**答案** (1) 22 A; (2) 4840 W""",
            "自由落体": """## 第4题
物体从80m高处自由落下。(g=10m/s²)
求：(1) 落地时间；(2) 落地速度。
**答案** (1) 4 s; (2) 40 m/s""",
        }
        for label, text in quick.items():
            if st.button(label, use_container_width=True):
                st.session_state.problem_text = text
                st.rerun()

    _, btn_col = st.columns([3, 1])
    with btn_col:
        start_review = st.button("🔍 开始审校", type="primary", use_container_width=True)

# ---- 结果区 ----
st.divider()
tab_report, tab_logs, tab_solver = st.tabs(["📋 最终校对报告", "🔍 主Agent 审校日志", "🤖 子Agent 独立求解日志"])

# ---- 状态管理 ----
if "logs" not in st.session_state:
    st.session_state.logs = []
if "solver_logs" not in st.session_state:
    st.session_state.solver_logs = []
if "final_report" not in st.session_state:
    st.session_state.final_report = ""


def add_log(level, title, detail="", elapsed_ms=0):
    st.session_state.logs.append({
        "level": level, "title": title, "detail": detail,
        "elapsed_ms": elapsed_ms, "time": time.time(),
    })


def build_logs_text(logs=None):
    """将所有日志格式化为纯文本"""
    if logs is None:
        logs = st.session_state.logs
    lines = []
    for log in logs:
        lv = log["level"]
        title = log["title"]
        detail = log["detail"]
        elapsed = log.get("elapsed_ms", 0)
        if lv == "info":
            lines.append(f"[INFO] {title}" + (f" ({elapsed}ms)" if elapsed else ""))
            if detail:
                lines.append(f"  {detail[:300]}")
        elif lv == "tool_call":
            lines.append(f"[TOOL] {title}")
            lines.append(f"  args: {detail}")
        elif lv == "tool_result":
            lines.append(f"[RESULT] {title}" + (f" ({elapsed}ms)" if elapsed else ""))
            lines.append(f"  {detail}")
        elif lv == "sandbox":
            lines.append(f"[SANDBOX] {title}\n{detail}")
        elif lv == "llm_output":
            lines.append(f"[LLM] {detail[:300]}...")
        elif lv == "error":
            lines.append(f"[ERROR] {title}\n{detail[:500]}")
        lines.append("")
    return "\n".join(lines)


def render_logs():
    with tab_logs:
        if not st.session_state.logs:
            st.info("点击「开始审校」后这里会显示每一步的执行日志")
            return

        # 一键复制按钮
        logs_text = build_logs_text()
        col_copy, col_empty = st.columns([1, 3])
        with col_copy:
            st.download_button(
                "📋 一键导出日志", data=logs_text,
                file_name=f"review_log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain", use_container_width=True,
            )

        for log in st.session_state.logs:
            lv = log["level"]
            if lv == "info":
                st.text(f"ℹ️ {log['title']}" + (f" ({log['elapsed_ms']}ms)" if log["elapsed_ms"] else ""))
                if log["detail"]:
                    st.caption(log["detail"][:200])
            elif lv == "tool_call":
                with st.expander(f"🔧 {log['title']}", expanded=False):
                    st.code(log["detail"], language="json")
            elif lv == "tool_result":
                with st.expander(f"📊 {log['title']}", expanded=False):
                    st.code(log["detail"], language="json")
                    if log.get("elapsed_ms"):
                        st.caption(f"⏱ {log['elapsed_ms']}ms")
            elif lv == "sandbox":
                with st.expander(f"🖥 {log['title']}", expanded=False):
                    st.code(log["detail"], language="python")
            elif lv == "llm_output":
                st.caption("💬 LLM 输出片段（完整报告见「最终校对报告」标签页）")
            elif lv == "error":
                st.error(f"{log['title']}\n{log['detail'][:500]}")


SYSTEM_PROMPT = """\
你是资深高中物理教研员，负责对物理题目进行严格校对。你有数学工具可以调用。

**关键前提：你要审校的题目绝大多数是纯符号推导题——没有具体数值，答案也是符号表达式。**

## 审校流程（按顺序执行）

### 第1-3部分：基础审核
对题目的文字、公式符号、题干严谨性进行全面检查。
这些部分不需要调用工具。

### 第4部分：解析内容审核 + 逐步工具验算
**逐步骤**跟踪题目给出的解析过程：每一步推导调用了什么公式、做了什么变形，都用工具逐一验证。
- 用 check_equality 验证推导中的等价变换是否正确
- 用 solve_physics_formula 验证公式重排
- 用 simplify_expression 验证化简步骤
- 判断解析逻辑是否自洽、有无跳步或逻辑漏洞

### 第5部分：独立求解 + 交叉比对（核心环节）
**用户消息末尾附带了子Agent独立求解的结果。子Agent在干净的对话上下文中运行，从未见过原解析，只根据题干独立推导。它的结果可作为真正的第三方参照。**

执行交叉比对：
1. 将子Agent独立求解结果、题目解析、题目答案三组数据进行对比
2. 列出每组的每个关键中间结果是否一致
3. 综合给出最终结论：
   - 三方一致 → 答案正确，高度可信
   - 子Agent与答案一致但与原解析不一致 → 原解析可能有推导错误
   - 子Agent与某方不一致 → 标注差异并分析原因
4. 如果有不一致，指出哪个环节有问题

**注意：你自己不要再重新推导一遍——子Agent已经做了这件事。你的职责是交叉比对三组结果。**

### 第6部分：校对总结
综合前 5 部分的发现，给出问题等级（无问题/轻微/一般/严重错误）。

## 工具使用策略

### check_equality —— 符号等价（最常用）
```
check_equality(expression_a="表达式A", expression_b="表达式B")
```
返回 True 表示两式恒等。先 simplify 再比较效果更好。

### solve_physics_formula —— 公式重排求解
```
solve_physics_formula(formula="原始公式", solve_for="目标变量")
```

### 量纲验证 —— 每道题第一步就做
```
dimensional_analysis(expression="F=m*a", operation="check_consistency", unit_definitions={...})
```
量纲不对则答案必然错误。符号题尤其适用。

### 禁止行为
- **禁止**用 evaluate_expression 代入自己编造的随机数字
- **禁止**编造 m=1, q=1, h=1 等"方便计算"的值
- 两个表达式在某个点数值相等 ≠ 恒等
- evaluate_expression 仅在题目给出具体数值时使用

## 输出格式
最终输出完整六段 Markdown 报告：
## 1. 文字内容校对
## 2. 公式与符号格式校对
## 3. 题干与情景严谨性评估
## 4. 解析内容审核（逐步骤跟踪原解析 + 工具验算）
## 5. 独立求解 + 交叉比对（独立推导 → 三方比对 → 综合结论）
## 6. 校对总结（问题等级 + 最终结论）
"""


@st.cache_resource
def get_agent():
    from sympy_tools import get_tools_for_langgraph
    return get_tools_for_langgraph()


def build_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model_name, openai_api_key=api_key,
        openai_api_base=api_url, temperature=temperature, timeout=300,
    )


def build_image_content(uploaded_file) -> dict | None:
    data = uploaded_file.getvalue()
    if len(data) > 10 * 1024 * 1024:
        st.warning(f"图片 {uploaded_file.name} >10MB，已跳过")
        return None
    mime = uploaded_file.type or "image/png"
    b64 = base64.b64encode(data).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


# 题干提取：遇到这些标记之前的内容就是"只含题干不含解析"
_PROBLEM_DELIMITERS = [
    "**解析**", "**解答**", "**解：**", "**解:**", "**解：", "**答案**",
    "## 解析", "## 解答", "## 答案",
    "【解析】", "【解答】", "【答案】",
    "\n解：", "\n解:", "\n答：", "\n答:",
    "解答：", "解答:", "解析：", "解析:",
]


def extract_problem_only(text: str) -> str:
    """从完整题目文本中提取纯题干（去掉解析和答案部分）"""
    best_idx = len(text)
    for delim in _PROBLEM_DELIMITERS:
        idx = text.find(delim)
        if idx != -1 and idx < best_idx:
            best_idx = idx
    return text[:best_idx].strip()


SOLVER_PROMPT = """\
你是高中物理教师，负责独立求解物理题。所有计算必须调用工具。题目绝大多数是纯符号推导题。

## 核心规则
1. 只看题干，不看已有解析
2. 每一步涉及计算时必须调用工具——包括公式代入、分数运算、化简
3. 最终答案用 check_equality 验证
4. 量纲分析每道题第一步就做

## 几何题：把所有几何转成坐标+代数
- 点用坐标: Point(x, y), 方向用向量: [vx, vy]
- 过点垂线/定圆 → geometry_construct
- 距离/夹角/交点 → geometry_measure
- 点积/叉积/夹角/投影 → vector_operations
- 磁场偏转圆心+半径 → magnetic_deflection 一步求解

## 禁止行为
- **禁止**编造数值代入（v0=3, m=1 等）
- **禁止**手动做角度推理——转成坐标+向量用工具算

## 可用工具（11个）
check_equality, simplify_expression, solve_physics_formula, solve_equation, dimensional_analysis, compute_limit, geometry_construct, geometry_measure, vector_operations, magnetic_deflection, evaluate_expression

## 输出格式
## 独立求解过程
（每步：物理原理 → 工具+参数 → 结果 → 物理含义）

## 独立求解答案
（表达式或数值 + 单位）
"""


def run_solver(problem_text: str, images: list | None = None, logs: list | None = None) -> str:
    """在干净的对话上下文中独立求解题目。返回求解过程和答案。"""
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.prebuilt import ToolNode
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

    if logs is None:
        logs = []

    llm = build_llm()
    tools = get_agent()
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def _agent(state):
        t0 = time.monotonic()
        resp = llm_with_tools.invoke(state["messages"])
        elapsed = int((time.monotonic() - t0) * 1000)
        tc_count = len(resp.tool_calls) if hasattr(resp, "tool_calls") and resp.tool_calls else 0
        logs.append({"level": "info", "title": f"子Agent LLM 响应 ({elapsed}ms)", "detail": f"tool_calls={tc_count}", "elapsed_ms": elapsed})
        if hasattr(resp, "tool_calls") and resp.tool_calls:
            for tc in resp.tool_calls:
                logs.append({"level": "tool_call", "title": tc["name"], "detail": json.dumps(tc.get("args", {}), ensure_ascii=False, indent=2), "elapsed_ms": 0})
        return {"messages": [resp]}

    def _route(state):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("solver", _agent)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "solver")
    graph.add_conditional_edges("solver", _route)
    graph.add_edge("tools", "solver")

    user_content = [{"type": "text", "text": f"请独立求解下面这道物理题：\n\n{problem_text}"}]
    if images:
        for img in images:
            user_content.append(img)

    compiled = graph.compile()
    output_parts = []
    try:
        for event in compiled.stream(
            {"messages": [SystemMessage(content=SOLVER_PROMPT), HumanMessage(content=user_content)]},
            stream_mode="updates",
        ):
            for node_data in event.values():
                for msg in node_data.get("messages", []):
                    if isinstance(msg, ToolMessage):
                        try:
                            data = json.loads(msg.content)
                            code = data.get("code", "")
                            if code:
                                logs.append({"level": "sandbox", "title": f"子Agent 沙箱 → {msg.name}", "detail": code, "elapsed_ms": data.get("elapsed_ms", 0)})
                            summary = {k: v for k, v in data.items() if k != "code"}
                            logs.append({"level": "tool_result", "title": f"{msg.name} → {str(data.get('result'))[:60]}", "detail": json.dumps(summary, ensure_ascii=False, indent=2), "elapsed_ms": data.get("elapsed_ms", 0)})
                        except Exception:
                            logs.append({"level": "tool_result", "title": msg.name, "detail": str(msg.content)[:500], "elapsed_ms": 0})
                    elif isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                        output_parts.append(msg.content)
    except Exception as e:
        logs.append({"level": "error", "title": "子Agent 执行异常", "detail": str(e), "elapsed_ms": 0})
        return f"[独立求解失败: {e}]"

    return "\n\n".join(output_parts).strip()


def run_review():
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.prebuilt import ToolNode
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

    st.session_state.logs = []
    st.session_state.solver_logs = []
    st.session_state.final_report = ""

    add_log("info", "初始化", f"题目 {len(problem_text)} 字符, 图片 {len(uploaded_files or [])} 张")

    # 提取纯题干
    problem_only = extract_problem_only(problem_text)
    add_log("info", "提取题干", f"原 {len(problem_text)} 字符 → 题干 {len(problem_only)} 字符")

    # 构建图片内容
    images = []
    if uploaded_files:
        for uf in uploaded_files:
            img = build_image_content(uf)
            if img:
                images.append(img)

    # ---- Phase 1: 子 Agent 独立求解 ----
    add_log("info", "子 Agent 独立求解开始", "干净的对话上下文，只看题干 + 图片")
    t0 = time.monotonic()
    try:
        solver_result = run_solver(problem_only, images if images else None, st.session_state.solver_logs)
        solver_elapsed = int((time.monotonic() - t0) * 1000)
        add_log("info", f"子 Agent 独立求解完成 ({solver_elapsed}ms)", solver_result[:300] + ("..." if len(solver_result) > 300 else ""))
    except Exception as e:
        solver_result = f"[独立求解失败: {e}]"
        add_log("error", "子 Agent 求解失败", str(e))
        solver_elapsed = 0

    # ---- Phase 2: 主 Agent 审校 ----
    add_log("info", "主 Agent 审校开始", "含子 Agent 独立求解结果作为 Step 5 对比依据")

    # 将子 Agent 结果注入用户消息
    user_text = problem_text
    if solver_result and "失败" not in solver_result:
        user_text += f"\n\n---\n**以下为子Agent独立求解结果，供Step 5交叉比对使用（此结果在干净上下文中生成，未见过原解析）：**\n\n{solver_result}"

    user_content = [{"type": "text", "text": user_text}]
    user_content.extend(images)

    try:
        llm = build_llm()
    except Exception as e:
        add_log("error", "LLM 初始化失败", str(e))
        return

    tools = get_agent()
    add_log("info", "工具就绪", f"{len(tools)} 个工具已绑定")

    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def _agent(state):
        t0 = time.monotonic()
        msgs = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=SYSTEM_PROMPT)] + msgs
        resp = llm_with_tools.invoke(msgs)
        elapsed = int((time.monotonic() - t0) * 1000)
        add_log("info", f"LLM 响应 ({elapsed}ms)", f"tool_calls={len(resp.tool_calls) if hasattr(resp, 'tool_calls') and resp.tool_calls else 0}")
        if hasattr(resp, "tool_calls") and resp.tool_calls:
            for tc in resp.tool_calls:
                add_log("tool_call", tc["name"], json.dumps(tc.get("args", {}), ensure_ascii=False, indent=2))
        return {"messages": [resp]}

    def _route(state):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", _agent)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _route)
    graph.add_edge("tools", "agent")

    compiled = graph.compile()
    initial = {"messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content if len(user_content) > 1 else user_text)]}

    # 收集最终报告
    report_parts = []
    try:
        for event in compiled.stream(initial, stream_mode="updates"):
            for node_name, node_data in event.items():
                for msg in node_data.get("messages", []):
                    if isinstance(msg, ToolMessage):
                        try:
                            data = json.loads(msg.content)
                            code = data.get("code", "")
                            if code:
                                add_log("sandbox", f"{msg.name} 代码", code)
                            summary = {k: v for k, v in data.items() if k != "code"}
                            add_log("tool_result",
                                    f"{msg.name} → success={data.get('success')}, result={str(data.get('result'))[:80]}",
                                    json.dumps(summary, ensure_ascii=False, indent=2),
                                    data.get("elapsed_ms", 0))
                        except (json.JSONDecodeError, TypeError):
                            add_log("tool_result", msg.name, str(msg.content)[:500])
                    elif isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                        report_parts.append(msg.content)
    except Exception as e:
        add_log("error", "执行异常", traceback.format_exc())

    # 合并最终报告
    final = "\n\n".join(report_parts)
    st.session_state.final_report = final
    add_log("info", "审校完成", f"报告 {len(final)} 字符")


# ---- 执行 ----
if start_review:
    if not problem_text.strip():
        st.error("请输入题目内容")
    elif not api_url or not api_key:
        st.error("请填写 API URL 和 Key")
    else:
        with st.spinner("审校中（LLM 推理 + 沙箱计算）..."):
            run_review()

def render_solver_logs():
    with tab_solver:
        if not st.session_state.solver_logs:
            st.info("点击「开始审校」后，子Agent 独立求解的日志会显示在这里")
            return
        solver_text = build_logs_text(st.session_state.solver_logs)
        st.download_button(
            "📋 导出子Agent日志", data=solver_text,
            file_name=f"solver_log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain", use_container_width=True,
        )
        for log in st.session_state.solver_logs:
            lv = log["level"]
            if lv == "info":
                st.text(f"ℹ️ {log['title']}" + (f" ({log['elapsed_ms']}ms)" if log.get("elapsed_ms") else ""))
                if log.get("detail"):
                    st.caption(log["detail"][:200])
            elif lv == "tool_call":
                with st.expander(f"🔧 子Agent: {log['title']}", expanded=False):
                    st.code(log["detail"], language="json")
            elif lv == "tool_result":
                with st.expander(f"📊 子Agent: {log['title']}", expanded=False):
                    st.code(log["detail"], language="json")
                    if log.get("elapsed_ms"):
                        st.caption(f"⏱ {log['elapsed_ms']}ms")
            elif lv == "sandbox":
                with st.expander(f"🖥 子Agent沙箱: {log['title']}", expanded=False):
                    st.code(log["detail"], language="python")
            elif lv == "error":
                st.error(f"子Agent: {log['title']}\n{log['detail'][:500]}")


# ---- 渲染 ----
with tab_report:
    if st.session_state.final_report:
        col1, col2 = st.columns([1, 4])
        with col1:
            st.download_button(
                "📥 下载报告", data=st.session_state.final_report,
                file_name=f"review_report_{time.strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown", use_container_width=True,
            )
        st.markdown(st.session_state.final_report)
    else:
        st.info("点击「开始审校」后，最终六段校对报告将显示在这里")

render_logs()
render_solver_logs()

st.divider()
st.caption(f"sympy_tools / LangGraph ReAct / doubao + Sandbox / {len(get_agent())} tools")
