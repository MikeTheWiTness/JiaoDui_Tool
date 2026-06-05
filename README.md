# 校对工具（JiaoDui Tool）

高中全学科题目处理流水线 —— Word 转 Markdown → 智能拆分 → AI 校对

## 功能概览

1. **格式转换**：Word `.docx` → Markdown（Pandoc，保留 LaTeX 数学公式）
2. **智能拆分**：按题目标题/题号拆分为独立目录，自动提取配图
3. **AI 校对**：调用 LLM API 对每道题目进行全方位审校，支持符号计算工具实算验证

支持两种来源模式：
- **讲义模式**：按标题模式（如 `**例1**`、`**清北班例题**`）拆分
- **试卷模式**：按题号（`1．`、`2．`）拆分，自适应答案位置

## 支持的学科（v1.5）

| 学科 | 符号计算工具 |
|------|-------------|
| 语文 | — |
| 数学 | 表达式求值、方程求解、等价判断、化简、极限 |
| 英语 | — |
| 物理 | 表达式求值、方程求解、公式求解、量纲分析、向量运算、磁场偏转 |
| 化学 | 表达式求值、方程求解、方程式配平、化学计量计算 |
| 生物 | 表达式求值、方程求解 |
| 政治 | — |
| 历史 | — |
| 地理 | — |

每学科有独立的两套 AI 提示词：**题目校对**（question）和**知识校对**（knowledge），存储在 `prompts/` 目录。

## 快速开始

```bash
# 安装依赖
pip install sympy requests

# 运行（GUI）
python 校对工具整合版v1.5.py
```

1. 点击 **⚙️ API 配置** 填写接口地址、密钥和模型名
2. 选择**来源模式**（讲义/试卷）和**学科**
3. 添加 Word 文件，点击**开始处理**

## 版本历史

### v1.5 — 多学科支持 + 符号计算工具集成

- 新增 9 学科独立 AI 提示词（`prompts/` 目录）
- GUI 新增学科选择下拉菜单，切换时自动重载提示词和工具
- 将 `sympy_tools` 符号计算工具接入 API 调用链：
  - 数学 5 工具、物理 6 工具、化学 4 工具、生物 2 工具
  - API 支持 function-calling 循环，模型可调用工具**实算验证**答案
- 新增化学符号计算工具：方程式配平（线性代数法）、化学计量计算
- 新增标题拆分模式：`变式N_例M`、`变式N`
- 修复 Windows 子进程 GBK 编码问题
- 窗口标题改为"多学科题目处理工具 v1.5"

### v1.4 — 符号计算工具包

- 新增 `sympy_tools/` 模块，提供 10 个符号计算工具：
  - `evaluate_expression` — 表达式求值
  - `solve_equation` — 方程求解
  - `check_equality` — 表达式等价判断
  - `simplify_expression` — 化简/展开/因式分解
  - `solve_physics_formula` — 物理公式求解
  - `dimensional_analysis` — 量纲分析
  - `compute_limit` — 极限计算
  - `geometry_construct` / `geometry_measure` — 几何构造与测量
  - `vector_operations` — 向量运算
  - `magnetic_deflection` — 磁场偏转（解析几何法）
- 代码沙箱：子进程隔离执行，安全检测拦截危险操作
- 整合版 GUI：三工具合一（讲义拆分 + 试卷拆分 + API 校对）

### v1.3 — 整合版基线

- 讲义拆分工具：Word → Markdown → 按标题模式拆题 + 提取知识
- 试卷拆分工具（组卷网格式）：自适应答案位置（随题/末尾）
- API 校对工具：物理题目 AI 审校（豆包模型 / 火山方舟 API）
- Pandoc 转换管线，LaTeX 数学公式保留
- `title_patterns.json` 可配置标题匹配规则

## 目录结构

```
校对v1.3/
├── 校对工具整合版v1.5.py   # 主程序（GUI）
├── API校对单讲拆分1.3.py    # 物理校对（旧版，独立运行）
├── 讲义拆分题目和知识转md.py # 讲义拆分（旧版，独立运行）
├── 组卷网试卷转md.py         # 试卷拆分（旧版，独立运行）
├── sympy_tools/             # 符号计算工具包（v1.4+）
│   ├── tools.py             # 工具定义（LangChain BaseTool）
│   ├── templates.py         # SymPy 代码生成模板
│   ├── sandbox.py           # 沙箱执行环境
│   └── safety.py            # 安全检测
├── prompts/                 # 学科提示词（v1.5）
│   ├── 语文.json
│   ├── 数学.json
│   ├── 英语.json
│   ├── 物理.json
│   ├── 化学.json
│   ├── 生物.json
│   ├── 政治.json
│   ├── 历史.json
│   └── 地理.json
├── title_patterns.json      # 讲义标题匹配规则
├── .env                     # API 配置（需自行创建）
└── output/                  # 默认输出目录
    ├── 拆题结果/
    └── 校对报告/
```

## 配置说明

### API 配置

在 GUI 中点击 **⚙️ API 配置** 填写，或手动创建 `.env` 文件：

```
API_URL=https://ark.cn-beijing.volces.com/api/v3
API_KEY=your-api-key
MODEL_NAME=your-model-id
```

### 讲义标题匹配规则

编辑 `title_patterns.json`，支持正则表达式：

```json
{
  "patterns": [
    "例\\d+",
    "练\\d+",
    "清北班\\d+",
    "变式\\d+",
    "变式\\d+_例\\d+"
  ]
}
```

匹配规则：行首出现 `**{pattern}**` 格式的加粗文本即视为题目标题。

## 数据流

```
.docx 文件
  → Pandoc → 原始 .md（+ _images/media/）
  → LaTeX 转义修复 / 后处理
  → 表格清理（讲义）或公式格式修正（试卷）
  → 拆分为 第N题/第N题.md + 第N题/images/
  → （可选）提取 知识/知识.md + 知识/images/
  → AI 校对（学科提示词 + 符号计算工具）→ _校对报告.md
```
