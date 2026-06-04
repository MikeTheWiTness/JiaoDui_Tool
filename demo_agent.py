"""
符号计算审校 Agent Demo

展示 6 个 SymPy 工具在 LangGraph ReAct 循环中的实际使用。
LLM: doubao-seed-2-0-pro（via Volces Ark，兼容 OpenAI function calling）
"""
import json
import os
import sys

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage

from sympy_tools import ALL_TOOLS, get_tools_for_langgraph

# ---- 配置 ----
API_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "api_config.json")


def load_api_config():
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


SYSTEM_PROMPT = """\
你是资深高中物理教研员，负责对物理题目进行严格校对。你有数学工具可以调用。

## 审校流程

### 第4部分：解析内容审核 + 逐步工具验算
逐步骤跟踪题目给出的解析，每一步推导都用工具验证，判断解析逻辑是否自洽。

### 第5部分：独立求解 + 交叉比对（核心）
暂时忽略题目解析，从题干出发独立求解。推导中遇到任何计算都调工具。
得到自己的答案后，与题目解析、题目答案进行三方交叉比对，给出综合结论。

## 工具策略
- check_equality: 符号等价验证（纯符号题首选）
- simplify_expression: 化简后便于等价比较
- solve_physics_formula: 从公式解出目标变量
- dimensional_analysis: 量纲验证（每道题第一步就做）
- 禁止编造数值代入

## 输出格式
## 1. 文字内容校对
## 2. 公式与符号格式校对
## 3. 题干与情景严谨性评估
## 4. 解析内容审核（逐步验算）
## 5. 独立求解 + 交叉比对
## 6. 校对总结
"""


def build_agent():
    """构建 LangGraph ReAct Agent。"""
    config = load_api_config()

    llm = ChatOpenAI(
        model=config["model"],
        openai_api_key=config["api_key"],
        openai_api_base=config["api_url"],
        temperature=0.3,
        timeout=120,
    )

    tools = get_tools_for_langgraph()
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: MessagesState) -> dict:
        messages = state["messages"]
        # 首条消息前插入系统提示
        if not any(isinstance(m, type(m)) for m in messages if hasattr(m, "role") and m.role == "system"):
            from langchain_core.messages import SystemMessage
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    def should_continue(state: MessagesState):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")

    return graph.compile()


def run_review(problem_text: str):
    """审校一道物理题，打印完整过程。"""
    agent = build_agent()
    result = agent.invoke({"messages": [HumanMessage(content=problem_text)]})

    print("=" * 60)
    print("审校结果")
    print("=" * 60)
    for msg in result["messages"]:
        if isinstance(msg, HumanMessage):
            print(f"\n📝 题目:\n{msg.content[:200]}...")
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"\n🔧 调用工具: {tc['name']}")
                    print(f"   参数: {json.dumps(tc['args'], ensure_ascii=False)}")
            if msg.content:
                print(f"\n📄 {msg.content}")
        elif hasattr(msg, "name") and hasattr(msg, "content"):
            print(f"\n📊 工具返回 ({msg.name}): {msg.content[:300]}")
    return result


# ---- Demo 题目 ----

DEMO_PROBLEMS = {
    "kinematics": """## 第1题
**例1** 一辆汽车从静止开始以恒定加速度运动，经过5秒后速度达到20 m/s。求：(1) 汽车的加速度；(2) 前5秒内的位移。

**解析** (1) 由 v = v₀ + at，v₀=0, t=5, v=20：
加速度 a = v/t = 20/5 = 4 m/s²

(2) 位移 s = v₀t + ½at² = 0 + ½×4×25 = 50 m

**答案** (1) 4 m/s²; (2) 50 m""",

    "energy": """## 第2题
**例2** 质量为2 kg的物体从地面以10 m/s的初速度竖直上抛。求物体上升到最高点时的机械能。(g=10 m/s²)

**解析** 最高点速度为零，动能全部转化为重力势能。
初始动能 Eₖ = ½mv² = ½×2×100 = 100 J
最高点 E = mgh = 2×10×5 = 100 J

**答案** 100 J""",
}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        # 快速模式：只测试工具注册，不调 LLM
        print("=== 工具注册验证 ===")
        tools = get_tools_for_langgraph()
        for t in tools:
            print(f"  {t.name}: {t.description[:60]}...")
        print(f"\n总计 {len(tools)} 个工具已注册")

        print("\n=== 快速工具测试 ===")
        from sympy_tools.tools import EvaluateExpressionTool
        t = EvaluateExpressionTool()
        r = json.loads(t._run(expression="sqrt(2*10*5)"))
        print(f"  sqrt(2*10*5) = {r['result']}")
        print(f"  期望: 10.0 → {'✓' if abs(r['result'] - 10) < 0.01 else '✗'}")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "dry":
        # 干跑模式：构建 agent 但不实际调用 LLM
        print("=== 构建 Agent ===")
        agent = build_agent()
        print(f"Agent 构建成功")
        print(f"工具数: {len(get_tools_for_langgraph())}")
        print(f"图节点: {list(agent.get_graph().nodes.keys())}")
        return

    # 完整模式：实际审校
    print("=== 符号计算审校 Agent Demo ===\n")
    for name, problem in DEMO_PROBLEMS.items():
        print(f"\n{'#' * 50}")
        print(f"# 审校: {name}")
        print(f"{'#' * 50}")
        try:
            run_review(problem)
        except Exception as e:
            print(f"\n❌ 审校失败: {e}")
        print("\n")


if __name__ == "__main__":
    main()
