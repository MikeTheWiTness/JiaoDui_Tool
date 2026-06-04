# PRD: 符号计算审校子 Agent

- **Status**: ready-for-agent

## Problem Statement

当前审校工具完全依赖 LLM 进行所有维度的审查——包括数值计算、公式推导和答案验证。LLM 作为语言模型，在数值计算和符号推导上存在根本性局限：凭概率估算而非确定性计算，会产生隐蔽的计算错误、单位混淆和推导失误。审校者需要逐条核对 LLM 的计算结论，这削弱了自动化审校的核心价值。

## Solution

在现有审校管道中嵌入一个基于 LangGraph ReAct 循环的符号计算子 Agent。该 Agent 审校时自主调用 SymPy 数学工具——代入验证、方程求解、表达式等价判断、量纲分析——以确定性符号计算替代 LLM 的统计推断，弥补 LLM 在计算维度的短板。

## Scope

### 本 PRD 涵盖

- 6 个 SymPy 符号计算 Tool（`BaseTool` 子类），覆盖高中物理审校所需的全部数学操作
- 隔离子进程沙箱执行层（安全黑名单 + 超时保护）
- LangGraph ReAct Agent（LLM 审校过程中自主决定调用 tool 的时机和频次）
- 增强序列化（处理 Matrix、Piecewise、Set 等复杂 SymPy 返回类型）
- 独立 Demo 脚本（不依赖 GUI，纯命令行运行验证物理题）
- 与现有 `code_sandbox.py` 向后兼容

### 后续 PRD 涵盖

- RAG 检索辅助审校（从知识图谱注入迷思概念和教学策略）
- EduAgent PrecisionReviewState 集成
- 拆分讲义/试卷的 pipeline 作为 tool 供主 Agent 调用
- Limit/Matrix/Diff/Integrate tool（高中物理极少用到）
- 进程复用优化（当前场景下一次调用开销可忽略）

## User Stories

1. As a **审校者**, I want 审校报告中的数值答案经过 SymPy 实算验证, so that 不会遗漏 LLM 的计算错误
2. As a **审校者**, I want 题目解析部分的方程求解经过符号计算校验, so that 推导步骤的正确性有确定性结论
3. As a **审校者**, I want 物理公式的量纲一致性被自动检查, so that 单位错误不会逃过审查
4. As a **Agent**, I want 在审校过程中自主判断何时需要调用数学工具, so that 只在必要时产生计算开销
5. As a **Agent**, I want 调用 tool 得到的结果能影响后续审校判断, so that 错误的计算结果能引导我给出更准确的审校意见
6. As a **系统**, I want 符号计算在隔离子进程中执行, so that 恶意或错误的数学表达式不会影响主进程稳定性
7. As a **开发者**, I want 每个 tool 用标准高中物理题可独立测试, so that 工具的正确性不依赖 LLM 行为
8. As a **开发者**, I want 现有 `code_sandbox.execute_verification()` 接口不被破坏, so that 已有的测试和调用代码继续工作

## Implementation Decisions

### Agent 架构

采用 ReAct 循环 + Function Calling 模式：

```
START → [审校 LLM] → 需要计算? → [ToolNode 执行] → [审校 LLM]
                    ↘ 不需要 → END
```

LLM 在输出六段审校报告的过程中随时插入 tool call。最终报告由多条消息合并拼接。doubao 模型确认支持 OpenAI 兼容的 `tools` 参数和 function calling。

### Tool 清单（6 个）

| Tool | 参数 | 用途 |
|------|------|------|
| `evaluate_expression` | `expression`, `substitutions` | 代入数值计算，验证答案 |
| `solve_equation` | `equations`, `variables`, `domain` | 符号/数值求解方程(组) |
| `check_equality` | `expression_a`, `expression_b` | 判断两表达式数学等价 |
| `simplify_expression` | `expression`, `method` | 化简/展开/三角化简 |
| `solve_physics_formula` | `formula`, `solve_for`, `known_values` | 从已知公式解出目标变量并代入求值 |
| `dimensional_analysis` | `expression`, `operation`, `unit_definitions` | 量纲一致性/维度提取/单位转换 |

每个 tool 直接继承 `langchain_core.tools.BaseTool`，`args_schema` 为 Pydantic BaseModel。迁入 EduAgent 时可直接注册到 `ToolNode`，无需适配器。

### 沙箱隔离

每次 tool call 启动一个新 Python 子进程执行 SymPy 代码：
- 安全黑名单预检查（18+ 危险模式正则，拦截 `os`/`subprocess`/`eval`/`open`/网络等）
- `subprocess.run([sys.executable, "-c", code], timeout=30)`
- 增强序列化器处理 Matrix、Piecewise、Set、bool、inf 等返回类型
- 每道题审校可能有 N 次 tool call = N 个子进程。当前场景下启动开销（~50ms）远小于 LLM API 延迟（~几秒），不做进程复用优化

### 文件结构

```
校对v1.3/
├── sympy_tools/              # 新包（独立于旧 code_sandbox.py）
│   ├── __init__.py           # ALL_TOOLS, get_tools_for_langgraph()
│   ├── safety.py             # 安全黑名单检查
│   ├── sandbox.py            # 子进程执行器
│   ├── templates.py          # SymPy 代码模板 + 序列化器
│   └── tools.py              # 6 个 BaseTool 子类实现
├── code_sandbox.py           # 保留，标记 deprecated，内部委托给 sympy_tools
├── tests/
│   ├── test_code_sandbox.py  # 保留，验证向后兼容
│   └── test_sympy_tools.py   # 新测试：每个 tool + 安全 + 序列化
├── demo_agent.py             # 最小 LangGraph ReAct Agent 演示
└── requirements.txt          # 追加 langchain-core（显式声明）
```

### System Prompt 设计

将当前 `API_Proofreading_Prompt.json` 拆分为两层消息：
1. **系统消息**：角色 + 六段报告格式 + **强制 tool 使用规则**（答案校验部分任何数值计算必须调用 `evaluate_expression`，不得凭模型记忆估算；推导必须调用 `solve_equation` 验证）
2. **用户消息**：题目内容 + 图片（不变）

### 与 EduAgent 对接

当前在校对v1.3 独立开发和测试。EduAgent 的 `PrecisionReviewState` 已定义（继承 `CoreState`，增加 `parsed_questions`、`kg_context`、`review_report`），但对应的节点工厂和 LangGraph 图尚未实现。符号计算 tool 成熟后直接作为 ToolNode 注册到 PrecisionReviewState 的工作流图中。

### 量纲分析的题目符号映射

高中物理题中常使用非标准物理量符号（如用 `l` 表示速度），`dimensional_analysis` 的 `unit_definitions` 参数支持 LLM 在调用时指定映射：`{"l": "meter/second", "t": "second"}`，解决符号歧义。

## Testing Decisions

### 测试分层

1. **安全层测试**：黑名单命中率、注入攻击防护、生成代码全量检查
2. **沙箱层测试**：Matrix/Piecewise/Set 序列化正确性、超时终止、语法错误优雅降级
3. **Tool 层测试**：每个 tool 用真实高中物理场景验证（具体数值而非仅检查 success 标志）
4. **Agent 层测试**：ToolNode 注册、ReAct 循环路由、tool call 消息格式
5. **向后兼容测试**：现有 `test_code_sandbox.py` 全部通过

### 测试策略

- 不测试 LLM 输出内容质量（通过 Demo 脚本人工验证）
- 不 mock SymPy——沙箱子进程本身就是轻量隔离，mock 反而增加维护负担
- 每个 tool 至少覆盖：正常输入 → 正确结果、异常输入 → 结构化错误、边界情况 → 确定行为

## Out of Scope

- RAG 检索辅助审校（后续 PRD）
- `differentiate` / `integrate` / `compute_limit` / `matrix_operation` tool（高中物理使用频率极低，后续按需添加）
- 审校报告自动格式化与排版优化（保持现有六段结构，格式由 LLM prompt 控制）
- GUI 集成（Demo 阶段纯命令行，GUI 集成在迁入 EduAgent 时完成）
- 批量审校并行化（单线程顺次处理）

## Further Notes

- 此 PRD 对应的实施计划见 `C:\Users\witne\.claude\plans\wondrous-roaming-petal.md`
- `dimensional_analysis` 作为 P1 中最高优先级——量纲分析是验证物理答案最经济的手段，一道题只需一次检查即可排除大量错误
- Tool 参数命名与物理教学语言对齐（`solve_for`、`known_values`、`substitutions`），降低 LLM 误用概率
- `code_sandbox.py` 保留向后兼容，调用代码无需修改。新开发使用 `sympy_tools` 包
