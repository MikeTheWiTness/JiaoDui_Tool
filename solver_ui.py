"""
子Agent 独立求解测试界面

只做一件事：给纯题干 + 图片，让子Agent 独立求解，展示完整的做题过程和工具调用。
"""
import base64
import json
import os
import time

import streamlit as st

st.set_page_config(page_title="子Agent 独立求解", page_icon="🧮", layout="wide")

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

    st.divider()
    st.header("题干提取")
    st.caption("自动按「解析」「答案」标记切分纯题干，也可手动编辑")
    auto_extract = st.checkbox("自动提取题干", value=True)

    st.divider()
    st.caption("10 工具: evaluate | solve | equality | simplify | physics_formula | dimensional | limit | geometry_construct | geometry_measure | vector_operations")

# ---- 标题 ----
st.title("🧮 子Agent 独立求解测试")
st.caption("干净对话上下文 · 只看题干 · 独立推导 · 每步调工具")

# ---- 输入区 ----
col_a, col_b = st.columns([2, 1])
with col_a:
    problem_text = st.text_area(
        "完整题目（含解析也不影响，会自动提取题干）",
        value=st.session_state.get("solver_problem", """## 第1题
一辆汽车从静止开始以加速度a=4m/s²运动，经过5秒。
求：(1) 末速度；(2) 位移。

**解析** (1) 由 v = v₀ + at，v₀=0, t=5, v=20：
v = a*t = 4*5 = 20 m/s

(2) s = v₀t + ½at² = 0 + ½*4*25 = 50 m

**答案** (1) 20 m/s; (2) 50 m"""),
        height=260,
    )

with col_b:
    uploaded_files = st.file_uploader("配图（可选）", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

    st.divider()
    st.caption("快捷测试题：")
    quick = {
        "运动学-匀加速": """## 第1题
一辆汽车从静止开始以加速度a=4m/s²运动，经过5秒。
求：(1) 末速度；(2) 位移。
**解析** v = a*t = 4*5 = 20 m/s。s = ½at² = 50 m
**答案** (1) 20 m/s; (2) 50 m""",
        "力学-竖直上抛": """## 第2题
质量为2kg的物体从地面以10m/s初速度竖直上抛。求最高点机械能。(g=10m/s²)
**解析** E = ½mv² = ½*2*100 = 100J
**答案** 100 J""",
        "电磁场-复合场": """## 第3题
带电粒子（质量m，电荷+q）在电场中加速后进入磁场偏转。
电场强度E，加速距离h。磁场中偏转半径R，求磁感应强度B。
**解析** qEh = ½mv² → v = √(2qEh/m)。qvB = mv²/R → B = mv/(qR)
**答案** B = √(2mEh/q)/R""",
    }
    for label, text in quick.items():
        if st.button(label, use_container_width=True):
            st.session_state.solver_problem = text
            st.rerun()

_, btn_col = st.columns([3, 1])
with btn_col:
    start_solve = st.button("🧮 开始独立求解", type="primary", use_container_width=True)

# ---- 结果区 ----
st.divider()
tab_answer, tab_logs = st.tabs(["📝 求解结果", "🔍 求解过程日志"])

# ---- 状态 ----
if "solver_logs" not in st.session_state:
    st.session_state.solver_logs = []
if "solver_answer" not in st.session_state:
    st.session_state.solver_answer = ""

# ---- 题干提取 ----
_PROBLEM_DELIMITERS = [
    "**解析**", "**解答**", "**解：**", "**解:**", "**答案**",
    "## 解析", "## 解答", "## 答案",
    "【解析】", "【解答】", "【答案】",
    "\n解：", "\n解:", "\n答：", "\n答:",
    "解答：", "解答:",  # 纯文本格式的解答标记
    "解析：", "解析:",
]


def extract_problem_only(text: str) -> str:
    best_idx = len(text)
    for delim in _PROBLEM_DELIMITERS:
        idx = text.find(delim)
        if idx != -1 and idx < best_idx:
            best_idx = idx
    return text[:best_idx].strip()


def add_log(level, title, detail="", elapsed_ms=0):
    st.session_state.solver_logs.append({
        "level": level, "title": title, "detail": detail,
        "elapsed_ms": elapsed_ms, "time": time.time(),
    })


SOLVER_PROMPT = """\
你是高中物理教师，负责独立求解物理题。你有数学工具，所有计算必须调用工具。

**关键前提：题目绝大多数是纯符号推导题——没有具体数值，答案也是符号表达式。**

## 核心规则
1. 只看题干，不看已有解析
0. **计算完成后必须逐条回查题目原文**：列出题干中描述的每一个物理过程（第几次进场、第几次碰撞、第几段运动），逐个核对你的计算是否覆盖了每一个过程。多一段或少一段都是错的。
2. 每一步推导涉及计算时必须调用工具——包括公式代入、分数运算、化简，不自认为"简单"就跳过
3. 最终答案用 check_equality 与推导结果比对，确认恒等后才能写"正确"
4. 量纲分析每道题第一步就做

## 几何题解题指南：把所有几何转成代数
任何几何场景（光学、电磁偏转、力学斜面）都按这个模式拆解：

### 第一步：用坐标描述所有已知点和方向
- 点用具体坐标: Point(x, y), 支持符号如 Point(1.5*h, 0)
- 方向用向量: [vx, vy]

### 第二步：用几何原语构造约束
- 过点做垂线 → geometry_construct: Line.perpendicular_line
- 构造圆 → geometry_construct: Circle(center, radius)
- 两点距离 → geometry_measure: Point.distance
- 直线/圆交点 → geometry_measure: intersection
- 向量点积/叉积/夹角 → vector_operations

### 第三步：用代数工具求解
- 已知公式重排 → solve_physics_formula
- 方程组求解 → solve_equation
- 表达式化简 → simplify_expression
- 验证推导 ＝ check_equality

### 电磁偏转专题
- 圆心在速度垂线上 + 圆心在撞击法线垂线上 → magnetic_deflection 一步求解
- 洛伦兹力: qvB = mv²/R → solve_physics_formula 解 B
- 周期: T = 2πR/v → check_equality 验证

### 光学专题
- 反射: vector_operations 求法向量 → geometry_construct 作对称线
- 折射: solve_physics_formula 代 n1sinθ1=n2sinθ2
- 光程: geometry_measure 求距离累加

### 禁止行为
- **禁止**编造数值代入（v0=3, m=1 等）
- **禁止**发明不存在的函数名
- **禁止**手动做角度推理——全部转成坐标+向量用工具算

## 可用工具（11个）
- check_equality: 符号等价验证（最常用）
- simplify_expression: 化简表达式
- solve_physics_formula: 公式重排+代入求解
- solve_equation: 方程/方程组求解
- dimensional_analysis: 量纲分析
- compute_limit: 极限分析
- geometry_construct: 构造几何对象
- geometry_measure: 距离/夹角/交点
- vector_operations: 点积/叉积/夹角/投影
- magnetic_deflection: 磁场偏转一步求解
- evaluate_expression: 代入数值（仅题目给具体数字时）

## 输出格式
## 独立求解过程
（每步标注：物理原理 → 工具名 + 参数 → 结果 → 物理含义）

## 过程回查
（列出题干的每个物理过程，逐一标注是否覆盖、时间是否正确）

## 最终答案
（表达式或数值 + 单位）
"""


@st.cache_resource
def get_agent():
    from sympy_tools import get_tools_for_langgraph
    return get_tools_for_langgraph()


def build_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model_name, openai_api_key=api_key,
        openai_api_base=api_url, temperature=0.3, timeout=300,
    )


def build_image_content(uploaded_file) -> dict | None:
    data = uploaded_file.getvalue()
    if len(data) > 10 * 1024 * 1024:
        return None
    mime = uploaded_file.type or "image/png"
    b64 = base64.b64encode(data).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def run_solver(problem_only: str, images: list | None = None):
    """独立求解"""
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.prebuilt import ToolNode
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

    st.session_state.solver_logs = []
    st.session_state.solver_answer = ""

    add_log("info", "子Agent 开始独立求解", f"题干 {len(problem_only)} 字符, 图片 {len(images or [])} 张")

    llm = build_llm()
    tools = get_agent()
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    add_log("info", f"工具就绪", f"{len(tools)} 个工具已绑定")

    def _agent(state):
        t0 = time.monotonic()
        resp = llm_with_tools.invoke(state["messages"])
        elapsed = int((time.monotonic() - t0) * 1000)
        tc_count = len(resp.tool_calls) if hasattr(resp, "tool_calls") and resp.tool_calls else 0
        add_log("info", f"LLM 响应 ({elapsed}ms)", f"tool_calls={tc_count}" + (f", content={len(resp.content)}字" if resp.content else ""))
        if resp.content:
            add_log("llm_text", "推理过程", resp.content[:2000])
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
    graph.add_node("solver", _agent)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "solver")
    graph.add_conditional_edges("solver", _route)
    graph.add_edge("tools", "solver")

    user_content = [{"type": "text", "text": f"请独立求解下面这道物理题：\n\n{problem_only}"}]
    if images:
        for img in images:
            user_content.append(img)

    compiled = graph.compile()
    answer_parts = []
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
                                add_log("sandbox", f"沙箱 → {msg.name}", code, data.get("elapsed_ms", 0))
                            summary = {k: v for k, v in data.items() if k != "code"}
                            add_log("tool_result",
                                    f"{msg.name} → success={data.get('success')}, result={str(data.get('result'))[:80]}",
                                    json.dumps(summary, ensure_ascii=False, indent=2),
                                    data.get("elapsed_ms", 0))
                        except Exception:
                            add_log("tool_result", msg.name, str(msg.content)[:500])
                    elif isinstance(msg, AIMessage) and msg.content:
                        # 收集所有推理文字（含 tool_calls 前后的推理）
                        answer_parts.append(msg.content)
    except Exception as e:
        add_log("error", "求解异常", str(e))
        st.session_state.solver_answer = f"[求解失败: {e}]"
        return

    st.session_state.solver_answer = "\n\n".join(answer_parts).strip()
    add_log("info", "求解完成", f"答案 {len(st.session_state.solver_answer)} 字符")


# ---- 渲染日志 ----
def render_logs():
    with tab_logs:
        if not st.session_state.solver_logs:
            st.info("点击「开始独立求解」后这里会显示每一步的执行日志")
            return

        # 导出按钮
        text_lines = []
        for log in st.session_state.solver_logs:
            lv = log["level"]
            text_lines.append(f"[{lv}] {log['title']}")
            if log.get("detail"):
                text_lines.append(f"  {log['detail'][:300]}")
            if log.get("elapsed_ms"):
                text_lines.append(f"  ({log['elapsed_ms']}ms)")
            text_lines.append("")
        st.download_button(
            "📋 导出日志", data="\n".join(text_lines),
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
            elif lv == "llm_text":
                with st.expander(f"💬 {log['title']}", expanded=True):
                    st.markdown(log["detail"])
            elif lv == "error":
                st.error(f"{log['title']}\n{log['detail'][:500]}")


# ---- 执行 ----
if start_solve:
    if not problem_text.strip():
        st.error("请输入题目内容")
    elif not api_url or not api_key:
        st.error("请填写 API URL 和 Key")
    else:
        problem_only = extract_problem_only(problem_text) if auto_extract else problem_text

        images = []
        if uploaded_files:
            for uf in uploaded_files:
                img = build_image_content(uf)
                if img:
                    images.append(img)

        # 显示提取结果
        if auto_extract:
            with st.expander(f"📋 自动提取的题干（{len(problem_only)} 字符）", expanded=False):
                st.text(problem_only[:2000])

        with st.spinner("子Agent 独立求解中（干净上下文，只看题干）..."):
            run_solver(problem_only, images if images else None)

# ---- 渲染 ----
with tab_answer:
    if st.session_state.solver_answer:
        col1, col2 = st.columns([1, 4])
        with col1:
            st.download_button(
                "📥 下载答案", data=st.session_state.solver_answer,
                file_name=f"solver_answer_{time.strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown", use_container_width=True,
            )
        st.markdown(st.session_state.solver_answer)
    else:
        st.info("点击「开始独立求解」后，子Agent 的完整推导过程和答案将显示在这里")

render_logs()

st.divider()
st.caption(f"solver_ui · 10 tools · 子Agent 独立求解 · 干净上下文")
