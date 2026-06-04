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

## 审校流程
1-3. 文字、公式符号、题干严谨性检查（无需工具）
4. 逐步骤跟踪题目解析过程，对每步推导调用工具验算
5. 将用户消息末尾附带的子Agent独立求解结果、题目解析、题目答案进行三方交叉比对，给出综合结论
6. 校对总结：问题等级（无问题/轻微/一般/严重错误）

## 规则
- check_equality 验证表达式等价，solve_physics_formula 验证公式重排
- dimensional_analysis 验证量纲一致性
- 禁止编造数值代入
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
你是高中物理教师，负责独立求解物理题。你有数学工具可以调用。

## 规则
1. 分析物理情景，写出推导过程和表达式
2. 遇到具体计算时调用工具，用工具返回的结果验证你的推导
3. 禁止编造数值代入，禁止发明不存在的函数名

## 工具
check_equality / simplify_expression / solve_equation / solve_physics_formula / dimensional_analysis / compute_limit / evaluate_expression / geometry_construct / geometry_measure / vector_operations / magnetic_deflection
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

    # ---- 并行执行：子Agent + 主Agent 同时启动 ----
    import concurrent.futures

    def _run_main_agent(user_content_for_main: list):
        """主 Agent 审校（Step 1-4），返回报告文本"""
        llm = build_llm()
        tools = get_agent()
        add_log("info", "主 Agent 审校开始", "与子Agent并行运行")
        llm_with_tools = llm.bind_tools(tools)
        tool_node = ToolNode(tools)

        def _agent(state):
            t0 = time.monotonic()
            msgs = list(state["messages"])
            msgs = [SystemMessage(content=SYSTEM_PROMPT)] + msgs
            resp = llm_with_tools.invoke(msgs)
            elapsed = int((time.monotonic() - t0) * 1000)
            add_log("info", f"主Agent LLM 响应 ({elapsed}ms)")
            if hasattr(resp, "tool_calls") and resp.tool_calls:
                for tc in resp.tool_calls:
                    add_log("tool_call", tc["name"], json.dumps(tc.get("args", {}), ensure_ascii=False, indent=2))
            return {"messages": [resp]}

        def _route(state):
            return "tools" if (isinstance(state["messages"][-1], AIMessage) and state["messages"][-1].tool_calls) else END

        graph = StateGraph(MessagesState)
        graph.add_node("agent", _agent)
        graph.add_node("tools", tool_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", _route)
        graph.add_edge("tools", "agent")

        initial = {"messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content_for_main)]}
        report_parts = []
        for event in graph.compile().stream(initial, stream_mode="updates"):
            for node_data in event.values():
                for msg in node_data.get("messages", []):
                    if isinstance(msg, ToolMessage):
                        try:
                            data = json.loads(msg.content)
                            if data.get("code"):
                                add_log("sandbox", f"{msg.name} 代码", data["code"])
                            summary = {k: v for k, v in data.items() if k != "code"}
                            add_log("tool_result", f"{msg.name} → {str(data.get('result'))[:60]}",
                                    json.dumps(summary, ensure_ascii=False, indent=2))
                        except Exception:
                            add_log("tool_result", msg.name, str(msg.content)[:300])
                    elif isinstance(msg, AIMessage) and msg.content:
                        report_parts.append(msg.content)
        return "\n\n".join(report_parts)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_solver = executor.submit(
            run_solver, problem_only, images if images else None, st.session_state.solver_logs
        )
        future_review = executor.submit(
            _run_main_agent, [{"type": "text", "text": problem_text}] + images
        )

        solver_result = future_solver.result()
        add_log("info", "子 Agent 独立求解完成", (solver_result or "")[:200])

        main_report = future_review.result()

    # 合并报告 + 交叉比对
    final_report = main_report
    if solver_result and "失败" not in solver_result:
        final_report += f"\n\n---\n\n## 子Agent 独立求解结果（供交叉比对）\n\n{solver_result}"
    st.session_state.final_report = final_report
    add_log("info", "审校完成", f"报告 {len(final_report)} 字符")


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
