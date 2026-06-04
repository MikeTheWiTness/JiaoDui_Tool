"""
三 Agent 校对架构

Agent 1 (校对): 完整题目 → 审校 Step 1-4
Agent 2 (求解): 纯题干+图 → 独立解题全过程
Agent 3 (校验+总结): A1+A2+题目 → Step 5-6

A1 + A2 并行 → A3 串行
"""
import base64
import json
import os
import time
import traceback
import threading

import streamlit as st

st.set_page_config(page_title="物理审校 Agent", page_icon="🔬", layout="wide")

# ---- 侧边栏 ----
with st.sidebar:
    st.header("API 配置")
    config_path = os.path.join(os.path.dirname(__file__), "api_config.json")
    saved_config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            saved_config = json.load(f)

    api_url = st.text_input("API URL", value=saved_config.get("api_url", ""))
    api_key = st.text_input("API Key", value=saved_config.get("api_key", ""), type="password")
    model_name = st.text_input("Model", value=saved_config.get("model", "doubao-seed-2-0-pro-260215"))
    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.05)

    st.divider()
    st.header("数据")
    st.session_state.setdefault("agent1_logs", [])
    st.session_state.setdefault("agent2_logs", [])
    st.session_state.setdefault("agent3_logs", [])
    st.session_state.setdefault("agent1_result", "")
    st.session_state.setdefault("agent2_result", "")
    st.session_state.setdefault("agent3_result", "")
    st.session_state.setdefault("final_report", "")

# ---- 标题 ----
st.title("🔬 三 Agent 物理审校")
st.caption("A1校对(1-4) ∥ A2求解 → A3校验+总结(5-6)")

# ---- 输入区 ----
with st.expander("📝 题目输入", expanded=True):
    col_a, col_b = st.columns([2, 1])
    with col_a:
        problem_text = st.text_area(
            "题目内容（Markdown）",
            value=st.session_state.get("problem_text", """## 第1题
一辆汽车从静止开始以加速度a=4m/s²运动，经过5秒。
求：(1) 末速度；(2) 位移。
**解析** v = a*t = 4*5 = 20 m/s。s = ½at² = 50 m
**答案** (1) 20 m/s; (2) 50 m"""),
            height=260,
        )
    with col_b:
        uploaded_files = st.file_uploader("配图（可选）", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        st.divider()
        st.caption("快捷测试题：")
        quick = {
            "匀加速": "一辆汽车从静止开始以加速度a=4m/s²运动，经过5秒。求：(1) 末速度；(2) 位移。\n**解析** v=4*5=20m/s。s=½*4*25=50m\n**答案** (1)20m/s;(2)50m",
            "竖直上抛": "质量为2kg的物体从地面以10m/s初速度竖直上抛。求最高点机械能。(g=10m/s²)\n**解析** E=½mv²=½*2*100=100J\n**答案** 100J",
            "欧姆定律": "电阻10Ω的导体两端加220V电压。求：(1)电流；(2)电功率。\n**解析** I=U/R=22A。P=UI=4840W\n**答案** (1)22A;(2)4840W",
            "自由落体": "物体从80m高处自由落下。(g=10m/s²)求：(1)落地时间；(2)落地速度。\n**解析** t=√(2h/g)=4s。v=gt=40m/s\n**答案** (1)4s;(2)40m/s",
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
tab_report, tab_a1, tab_a2, tab_a3 = st.tabs([
    "📋 最终校对报告", "🔍 A1 校对日志", "🤖 A2 求解日志", "⚖️ A3 校验日志"
])

# ---- 题干提取 ----
_PROBLEM_DELIMITERS = [
    "**解析**", "**解答**", "**解：**", "**解:**", "**解：", "**答案**",
    "## 解析", "## 解答", "## 答案",
    "【解析】", "【解答】", "【答案】",
    "\n解：", "\n解:", "\n答：", "\n答:",
    "解答：", "解答:", "解析：", "解析:",
]


def extract_problem_only(text: str) -> str:
    best_idx = len(text)
    for delim in _PROBLEM_DELIMITERS:
        idx = text.find(delim)
        if idx != -1 and idx < best_idx:
            best_idx = idx
    return text[:best_idx].strip()


# ---- Log helpers (thread-safe) ----
def _append_log(logs: list, level: str, title: str, detail: str = "", elapsed_ms: int = 0):
    logs.append({"level": level, "title": title, "detail": detail, "elapsed_ms": elapsed_ms})


def render_agent_logs(logs: list, prefix: str):
    if not logs:
        st.info("暂无日志")
        return
    for log in logs:
        lv, title, detail, elapsed = log["level"], log["title"], log.get("detail", ""), log.get("elapsed_ms", 0)
        if lv == "info":
            st.text(f"ℹ️  {title}" + (f" ({elapsed}ms)" if elapsed else ""))
            if detail:
                st.caption(detail[:200])
        elif lv == "tool_call":
            with st.expander(f"🔧 {title}", expanded=False):
                st.code(detail, language="json")
        elif lv == "tool_result":
            with st.expander(f"📊 {title}", expanded=False):
                st.code(detail, language="json")
                if elapsed:
                    st.caption(f"⏱ {elapsed}ms")
        elif lv == "sandbox":
            with st.expander(f"🖥 {title}", expanded=False):
                st.code(detail, language="python")
        elif lv == "llm_output":
            pass
        elif lv == "error":
            st.error(f"{title}\n{detail[:500]}")


# ---- Three Prompts ----

PROOFREAD_PROMPT = """\
你是资深高中物理教研员。你有数学工具可以调用。

## 任务：对题目进行审校，输出六段报告的前 4 段

1. 文字内容校对：错别字、漏字、语病、标点
2. 公式与符号格式校对：物理公式、单位、矢量符号、上下标
3. 题干与情景严谨性评估：物理情景、条件完整性
4. 解析内容审核：逐步骤跟踪题目解析过程，每步推导都用工具验算
   - 用 check_equality 验证等价变换
   - 用 solve_physics_formula 验证公式重排
   - 用 simplify_expression 验证化简
   - 用 dimensional_analysis 验证量纲
   - 用 magnetic_deflection 求解几何参数

## 规则
- 禁止编造数值代入
- 遇到计算必须调工具
"""

SOLVER_PROMPT = """\
你是高中物理教师，独立求解物理题。你有数学工具可以调用。

## 规则
1. 只看题干，不看已有解析
2. 分析物理情景，写出推导过程
3. 遇到计算时调用工具，用工具返回的结果验证
4. 禁止编造数值代入，禁止发明不存在的函数名

## 工具
check_equality / simplify_expression / solve_equation / solve_physics_formula / dimensional_analysis / compute_limit / evaluate_expression / geometry_construct / geometry_measure / vector_operations / magnetic_deflection
"""

ARBITER_PROMPT = """\
你是物理老师，正在批改一道题。你手上有三份材料：
1. 题目原文（含标准答案）
2. 一位学生的解答（独立完成，从未看过标准答案）
3. 一份对题目文字/符号/格式/解析的初步审校结果

## 任务：判断答案正确性并给出校对总结

**规则：**
1. 比较学生解答和标准答案的最终结果
2. 不需要重新审校文字、符号、格式——那些已经在"初步审校结果"中完成了
3. **如果学生对、标准答案对**：输出学生的完整解答过程作为正确参考
4. **如果学生对、标准答案错**：输出学生的解答过程，在总结中标注"标准答案有误，学生答案正确"
5. **如果学生错、标准答案对**：输出标准答案的解答过程，在总结中指出学生错在哪里
6. **如果两者都错**：你亲自给出正确解答，指出双方各自的问题
7. 判断完成后，给出校对总结（问题等级：无问题/轻微/一般/严重错误）

## 输出格式
## 5. 答案正确性校验
（学生答案 vs 标准答案的对比判断，最终采纳的解答过程）

## 6. 校对总结
（问题等级 + 最终结论）
"""


# ---- Agent 图工厂 ----
@st.cache_resource
def get_agent():
    from sympy_tools import get_tools_for_langgraph
    return get_tools_for_langgraph()


def build_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model_name, openai_api_key=api_key, openai_api_base=api_url, temperature=temperature, timeout=300)


def build_image_content(uploaded_file) -> dict | None:
    data = uploaded_file.getvalue()
    if len(data) > 10 * 1024 * 1024:
        return None
    mime = uploaded_file.type or "image/png"
    b64 = base64.b64encode(data).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _run_agent(user_content: list, system_prompt: str, logs: list, with_tools: bool = True) -> str:
    """通用 Agent 执行器：构建 LangGraph ReAct 循环，收集日志，返回最终文本输出"""
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.prebuilt import ToolNode
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

    llm = build_llm()
    tools = get_agent()
    llm_bound = llm.bind_tools(tools) if with_tools else llm
    tool_node = ToolNode(tools) if with_tools else None

    def _agent(state):
        t0 = time.monotonic()
        msgs = [SystemMessage(content=system_prompt)] + list(state["messages"])
        resp = llm_bound.invoke(msgs)
        elapsed = int((time.monotonic() - t0) * 1000)
        tc_count = len(resp.tool_calls) if hasattr(resp, "tool_calls") and resp.tool_calls else 0
        _append_log(logs, "info", f"LLM ({elapsed}ms)", f"tool_calls={tc_count}")
        if hasattr(resp, "tool_calls") and resp.tool_calls:
            for tc in resp.tool_calls:
                _append_log(logs, "tool_call", tc["name"], json.dumps(tc.get("args", {}), ensure_ascii=False, indent=2))
        return {"messages": [resp]}

    def _route(state):
        last = state["messages"][-1]
        if with_tools and isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", _agent)
    if with_tools:
        graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _route)
    if with_tools:
        graph.add_edge("tools", "agent")

    initial = {"messages": [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]}
    output_parts = []
    for event in graph.compile().stream(initial, stream_mode="updates"):
        for node_data in event.values():
            for msg in node_data.get("messages", []):
                if isinstance(msg, ToolMessage):
                    try:
                        data = json.loads(msg.content)
                        if data.get("code"):
                            _append_log(logs, "sandbox", f"沙箱 → {msg.name}", data["code"], data.get("elapsed_ms", 0))
                        summary = {k: v for k, v in data.items() if k != "code"}
                        _append_log(logs, "tool_result", f"{msg.name} → {str(data.get('result'))[:60]}",
                                    json.dumps(summary, ensure_ascii=False, indent=2), data.get("elapsed_ms", 0))
                    except Exception:
                        _append_log(logs, "tool_result", msg.name, str(msg.content)[:300])
                elif isinstance(msg, AIMessage) and msg.content:
                    output_parts.append(msg.content)
    return "\n\n".join(output_parts)


# ---- 主流程：三 Agent 审校 ----
def run_review():
    import concurrent.futures

    # 清空状态
    st.session_state.agent1_logs = []
    st.session_state.agent2_logs = []
    st.session_state.agent3_logs = []
    st.session_state.agent1_result = ""
    st.session_state.agent2_result = ""
    st.session_state.agent3_result = ""
    st.session_state.final_report = ""

    # 准备输入
    images = []
    if uploaded_files:
        for uf in uploaded_files:
            img = build_image_content(uf)
            if img:
                images.append(img)

    problem_only = extract_problem_only(problem_text)
    full_content = [{"type": "text", "text": problem_text}] + images
    problem_content = [{"type": "text", "text": problem_only}] + images

    a1_logs, a2_logs, a3_logs = [], [], []

    # ---- A1 + A2 并行 ----
    def _a1():
        _append_log(a1_logs, "info", "A1 校对开始", f"完整题目 {len(problem_text)} 字符")
        return _run_agent(full_content, PROOFREAD_PROMPT, a1_logs, with_tools=True)

    def _a2():
        _append_log(a2_logs, "info", "A2 求解开始", f"纯题干 {len(problem_only)} 字符")
        return _run_agent(problem_content, SOLVER_PROMPT, a2_logs, with_tools=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f1, f2 = ex.submit(_a1), ex.submit(_a2)
        a1_result = f1.result()
        a2_result = f2.result()

    # ---- A3 串行（无需工具） ----
    _append_log(a3_logs, "info", "A3 开始", "合并 A1+A2 结果")
    arbiter_input = [
        {"type": "text", "text": f"""## 题目原文（含标准答案）
{problem_text}

---
## 学生的解答（独立完成，未看过标准答案）
{a2_result}

---
## 初步审校结果（文字/符号/格式/解析已审）
{a1_result}

请根据以上信息，完成答案正确性校验和校对总结。"""}
    ]
    a3_result = _run_agent(arbiter_input, ARBITER_PROMPT, a3_logs, with_tools=False)

    # ---- 合并最终报告 ----
    final = f"""{a1_result}

---

{a3_result}"""
    st.session_state.agent1_logs = a1_logs
    st.session_state.agent2_logs = a2_logs
    st.session_state.agent3_logs = a3_logs
    st.session_state.agent1_result = a1_result
    st.session_state.agent2_result = a2_result
    st.session_state.agent3_result = a3_result
    st.session_state.final_report = final


# ---- 执行 ----
if start_review:
    if not problem_text.strip():
        st.error("请输入题目内容")
    elif not api_url or not api_key:
        st.error("请填写 API URL 和 Key")
    else:
        with st.spinner("三 Agent 审校中（A1校对 ∥ A2求解 → A3校验总结）..."):
            run_review()

# ---- 渲染 ----
with tab_report:
    if st.session_state.final_report:
        st.download_button("📥 下载报告", data=st.session_state.final_report,
                           file_name=f"review_{time.strftime('%Y%m%d_%H%M%S')}.md",
                           mime="text/markdown", use_container_width=True)
        st.markdown(st.session_state.final_report)
    else:
        st.info("点击「开始审校」后将显示完整六段校对报告")

with tab_a1:
    st.caption("Agent 1: 审校 Step 1-4（文字/符号/严谨性/解析）")
    render_agent_logs(st.session_state.agent1_logs, "A1")

with tab_a2:
    st.caption("Agent 2: 独立求解（纯题干，无解析）")
    render_agent_logs(st.session_state.agent2_logs, "A2")

with tab_a3:
    st.caption("Agent 3: 校验+总结 Step 5-6（无需工具）")
    render_agent_logs(st.session_state.agent3_logs, "A3")

st.divider()
st.caption(f"三 Agent · 11 tools · {len(get_agent())} 工具已注册")
