# 校对工具（JiaoDui Tool）

K-12 全学科题目处理流水线 —— Word 转 Markdown → 智能拆分 → AI 校对

## 功能概览

1. **格式转换**：Word `.docx` → Markdown（Pandoc，保留 LaTeX 数学公式）
2. **智能拆分**：两种模式自适应不同学科
   - **题目模式**（理科）：按粗体标题标记拆为独立单题
   - **版块模式**（英语）：按章节标题拆为教学版块
3. **AI 校对**：调用 LLM API（`reasoning_effort: high`），支持符号计算工具实算验证

支持两种文档来源：
- **讲义模式**：按学科配置拆分（title/section 两种子模式）
- **试卷模式**：按题号（`1．`、`2．`）拆分，自适应答案位置

## 学段与学科

| 学段 | 学科数 | 学科列表 |
|------|--------|---------|
| 小学 | 5 | 语文、数学、英语、科学、道法 |
| 初中 | 10 | 语文、数学、英语、物理、化学、生物、科学、道法、历史、地理 |
| 高中 | 9 | 语文、数学、英语、物理、化学、生物、政治、历史、地理 |

每学科+学段有独立配置文件（`subjects/{学段}/{学科}/config.json`），包含 AI 提示词和拆分规则。

| 学科 | 符号计算工具 | 拆分模式 |
|------|-------------|---------|
| 语文 | — | title |
| 数学 | 表达式求值、方程求解、等价判断、化简、极限 | title |
| 英语 | — | **section**（按章节拆版块，跳过知识提取） |
| 物理 | 表达式求值、方程求解、公式求解、量纲分析、向量运算、磁场偏转 | title |
| 化学 | 表达式求值、方程求解、方程式配平、化学计量计算 | title |
| 生物 | 表达式求值、方程求解 | title |
| 政治/道法 | — | title |
| 历史 | — | title |
| 地理 | — | title |
| 科学 | — | title |

## 快速开始

```bash
# 安装依赖
pip install sympy requests

# 运行整合版（推荐，含转换 + 拆分 + 校对）
python 校对工具整合版v1.5.py

# 或运行独立校对工具（仅校对，适合已有拆分结果的目录）
python API校对单讲拆分1.5.py
```

1. 点击 **⚙️ API 配置** 填写接口地址、密钥和模型名（自动保存到 `.env`）
2. 选择**学段**（小学/初中/高中）和**学科**
3. 选择文档**来源**（讲义/试卷）和**执行模式**
4. 添加 Word 文件，点击**开始处理**

## 版本历史

### v1.6 — 学段分级 + 版块拆分模式

- 重构配置目录：`subjects/{小学/初中/高中}/{学科}/config.json`，共 24 个配置文件
- 新增 `subject_config.py` 统一配置加载模块（回退兼容旧 `prompts/` 和 `title_patterns.json`）
- GUI 改为双下拉菜单：学段选择 + 学科选择，学科列表随学段动态更新
- 新增 **section 拆分模式**（英语讲义）：
  - 按 `##` 章节标题拆分为完整教学版块（`板块N/` 目录）
  - 自动跳过知识提取（版块本身即完整教学单元）
  - 提示词适配版块校对（输出"版块基础信息"而非"题目基础信息"）
- 初中政治 → 道法；新增小学/初中科学和道法
- `API校对单讲拆分1.5.py` 改为读取 `.env`（与整合版统一）
- 修复切换学段时学科列表未联动、转换全部失败时按钮卡住等问题
- `reasoning_effort: "high"` 思考模式已启用

### v1.5 — 多学科支持 + 符号计算工具集成

- 新增 9 学科独立 AI 提示词（`prompts/` 目录）
- GUI 新增学科选择下拉菜单，切换时自动重载提示词和工具
- 将 `sympy_tools` 符号计算工具接入 API 调用链
- 新增化学符号计算工具：方程式配平、化学计量计算
- 新增标题拆分模式：`变式N_例M`、`变式N`
- `API校对单讲拆分1.5.py` 同步升级为多学科工具

### v1.4 — 符号计算工具包

- 新增 `sympy_tools/` 模块（10 个工具）
- 代码沙箱：子进程隔离执行，安全检测

### v1.3 — 整合版基线

- 三工具合一（讲义拆分 + 试卷拆分 + API 校对）
- Pandoc 转换管线，LaTeX 数学公式保留
- `title_patterns.json` 可配置标题匹配规则

## 目录结构

```
校对v1.5/
├── 校对工具整合版v1.5.py       # 主程序（转换 + 拆分 + 校对，GUI）
├── API校对单讲拆分1.5.py        # 独立校对工具（仅校对，GUI）
├── 讲义拆分题目和知识转md.py    # 讲义拆分（独立运行，GUI）
├── 组卷网试卷转md.py            # 试卷拆分（独立运行，GUI）
├── subject_config.py           # 统一配置加载模块（v1.6）
├── subjects/                   # 学段+学科配置（v1.6）
│   ├── 小学/（语文、数学、英语、科学、道法）
│   ├── 初中/（语数外理化生科道历地）
│   └── 高中/（语数外理化生政历地）
│       └── {学科}/config.json  # 提示词 + 拆分规则
├── sympy_tools/                # 符号计算工具包
│   ├── tools.py, templates.py, sandbox.py, safety.py
├── prompts/                    # 旧版学科提示词（高中回退用）
├── tests/test_sympy_tools.py
├── API_Proofreading_Prompt.json   # 旧版物理提示词（回退用）
├── API_Knowledge_Prompt.json      # 旧版物理知识提示词（回退用）
├── title_patterns.json            # 旧版标题匹配规则（回退用）
├── .env                           # API 配置
├── CLAUDE.md
└── output/
    ├── 拆题结果/
    │   ├── {讲义名}/板块1/...   # section 模式
    │   └── {讲义名}/第1题/...   # title 模式
    └── 校对报告/
```

## 配置说明

### API 配置

在 GUI 中点击 **⚙️ API 配置** 填写，或手动创建 `.env` 文件：

```
API_URL=https://ark.cn-beijing.volces.com/api/v3
API_KEY=your-api-key
MODEL_NAME=doubao-seed-2-0-pro-260215
```

### 学科配置

每个学段+学科一个 `subjects/{学段}/{学科}/config.json`：

```json
{
  "question_prompt_lines": ["系统提示词行..."],
  "knowledge_prompt_lines": ["知识提示词行..."],
  "lecture_split": {
    "split_mode": "title",
    "wrapped_patterns": ["例\\d+", "练\\d+"],
    "unwrapped_patterns": [],
    "section_boundary": true
  },
  "exam_split": {
    "question_pattern": "^(\d+)．"
  }
}
```

- `split_mode: "section"` + `section_pattern: "^##\\s"` 启用英语版块拆分
- 缺失字段自动回退到旧 `prompts/{学科}.json` / `title_patterns.json`

## 数据流

```
.docx 文件
  → Pandoc → 原始 .md（+ _images/media/）
  → LaTeX 转义修复 / 后处理
  → 表格清理（讲义）或公式格式修正（试卷）
  → 拆分：
      title 模式   → 第N题/第N题.md + images/ + 知识/
      section 模式 → 板块N/板块N.md + images/
  → AI 校对（学科+学段提示词 + 符号计算工具 + reasoning_effort=high）
  → _校对报告.md
```
