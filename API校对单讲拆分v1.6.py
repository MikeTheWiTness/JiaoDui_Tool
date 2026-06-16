import os, sys
import json
import base64
import time
import threading
import re
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import requests
try:
    from pydantic import BaseModel, Field
    _PYDANTIC_OK = True
except ImportError:
    _PYDANTIC_OK = False
import subject_config


def _extract_json(text: str) -> dict | None:
    """从 LLM 返回文本中提取 JSON 对象。

    处理三种情况：
    1. 裸 JSON 对象 {...}
    2. Markdown 代码块包裹的 JSON ```json ... ```
    3. 文本中嵌入的 JSON 对象

    自动修复 LLM 常见的非法 JSON 转义（如 \\mathrm 写成 \mathrm）。
    """
    if not text:
        return None

    text = text.strip()

    # 尝试 1：直接解析
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 尝试 2：提取 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        block = m.group(1).strip()
        if block.startswith("{"):
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                pass

    # 尝试 3：提取 { 到 } 之间的内容，修复非法反斜杠
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        json_str = _fix_json_escapes(text[start:end + 1])
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    return None


def _fix_json_escapes(s: str) -> str:
    """修复 JSON 字符串中非法的反斜杠转义。

    LLM 常输出 LaTeX 命令如 \\sin、\\mathrm，但 JSON 中 \\s、\\m 等不是合法转义。
    将非法转义的 \\ 替换为 \\\\。
    合法转义：\\\" \\\\ \\/ \\b \\f \\n \\r \\t 及 \\uXXXX
    """
    VALID = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'}
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            next_ch = s[i + 1]
            if next_ch not in VALID:
                result.append('\\\\')
            else:
                result.append('\\')
            i += 1
        else:
            result.append(s[i])
        i += 1
    return ''.join(result)


def _save_proofread_json(res: str, q_dir: str):
    """尝试从 LLM 返回结果中提取 JSON 并保存为 _校对数据.json"""
    data = _extract_json(res)
    if data is None:
        return False

    json_path = os.path.join(q_dir, "_校对数据.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _app_path(rel):
    return os.path.join(_app_dir(), rel)

ENV_FILE = _app_path(".env")

# ========================= 符号计算工具集成 =========================
try:
    from sympy_tools.tools import (
        EvaluateExpressionTool, SolveEquationTool, CheckEqualityTool,
        SimplifyExpressionTool, SolvePhysicsFormulaTool, DimensionalAnalysisTool,
        ComputeLimitTool, VectorOperationsTool, CircleFromTwoPointsTool,
        GeometryTool, BalanceChemicalEquationTool, StoichiometryCalcTool,
    )
    _TOOLS_AVAILABLE = True
except ImportError:
    _TOOLS_AVAILABLE = False

try:
    from web_tools import WebFetchTool, WebSearchTool
    _WEB_TOOLS_OK = True
except ImportError:
    _WEB_TOOLS_OK = False

def _build_tool_map():
    if not _TOOLS_AVAILABLE:
        return {}
    return {
        "数学": [
            EvaluateExpressionTool(), SolveEquationTool(), CheckEqualityTool(),
            SimplifyExpressionTool(), ComputeLimitTool(),
            GeometryTool(), VectorOperationsTool(), CircleFromTwoPointsTool(),
        ],
        "物理": [
            EvaluateExpressionTool(), SolveEquationTool(), SolvePhysicsFormulaTool(),
            DimensionalAnalysisTool(), VectorOperationsTool(), CircleFromTwoPointsTool(),
        ],
        "化学": [
            EvaluateExpressionTool(), SolveEquationTool(),
            BalanceChemicalEquationTool(), StoichiometryCalcTool(),
        ],
        "生物": [
            EvaluateExpressionTool(), SolveEquationTool(),
        ],
    }

SUBJECT_TOOLS = _build_tool_map()

# 注册联网工具
if _WEB_TOOLS_OK:
    _wf = WebFetchTool()
    _ws = WebSearchTool()
    SUBJECT_TOOLS.setdefault("语文", []).extend([_wf, _ws])
    for _subj in ["数学", "物理", "化学", "生物"]:
        SUBJECT_TOOLS.setdefault(_subj, []).append(_ws)


def _tool_to_openai(tool):
    schema = tool.args_schema.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        }
    }

def _execute_tool(tool_instances, tool_name, arguments):
    for t in tool_instances:
        if t.name == tool_name:
            try:
                return t._run(**arguments)
            except Exception as e:
                return f"工具执行错误: {e}"
    return f"未知工具: {tool_name}"

def _get_tool_instructions(subject):
    if subject not in SUBJECT_TOOLS or not SUBJECT_TOOLS[subject]:
        return ""
    tools = SUBJECT_TOOLS[subject]
    sympy_tools = [t for t in tools if t.name != "web_search" and t.name != "web_fetch"]
    web_tools = [t for t in tools if t.name == "web_search" or t.name == "web_fetch"]

    lines = []

    # 语文学科 — 原文检索
    if subject == "语文":
        lines.append("\n## 可用的网页检索工具\n"
            "你在校对语文学科题目时，必须使用以下工具进行**原文联网检索和比对**，不得凭模型自身记忆判断原文准确性：\n")
        lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in web_tools))
        lines.append("\n使用规则：\n"
            "1. 遇到文言文/诗歌原文，必须调用 web_fetch 联网检索原文并逐字比对\n"
            "2. 先调 web_search 搜索'原文句子 site:sou-yun.cn'定位收录站点，再调 web_fetch 抓详情\n"
            "3. 搜索时必须直接用题目中原文的连续2-3句（至少15字）作为检索词，不要搜篇名标题\n"
            "4. 搜韵网 URL 格式：https://sou-yun.cn/QueryPoem.aspx?q=诗句\n"
            "5. 识典古籍搜索 URL 格式：https://www.shidianguji.com/search/原文句子?page_from=home_page\n"
            "6. 如果两次搜索均返回空或失败，标注'无法联网检索'并使用模型自身知识继续校对\n"
            "7. 仅文字类问题（错别字、语病等）不需要调用工具\n")
        return "".join(lines)

    # 其他学科 — 符号计算 + 联网搜索
    if sympy_tools:
        lines.append("\n## 可用的符号计算工具\n"
            "你在校对该学科题目时，可以使用以下工具进行**实算验证**，不得凭模型自身估算数值结果：\n")
        lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in sympy_tools))
        lines.append("\n使用规则：对于需要数值计算、方程求解、公式推导验证的步骤，必须调用对应工具获取精确结果。\n")

    if web_tools:
        lines.append("\n## 可用的联网搜索工具\n"
            "如需查找最新说法、验证专业术语、检索不在训练数据内的信息，可使用：\n")
        lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in web_tools))
        lines.append("\n使用规则：先调 web_search 搜索，若需查看详情页再调 web_fetch 抓取。"
            "搜索失败或超时是正常情况，此时使用模型自身知识继续。\n")

    return "".join(lines)

# ========================= 提示词加载 =========================

def load_subject_question_prompt(subject, level=None):
    return subject_config.get_question_prompt(subject, level)

def load_subject_knowledge_prompt(subject, level=None):
    return subject_config.get_knowledge_prompt(subject, level)

def get_full_question_prompt(subject, level=None):
    base = load_subject_question_prompt(subject, level)
    tool_instructions = _get_tool_instructions(subject)
    return base + tool_instructions if tool_instructions else base

def get_full_knowledge_prompt(subject, level=None):
    base = load_subject_knowledge_prompt(subject, level)
    tool_instructions = _get_tool_instructions(subject)
    return base + tool_instructions if tool_instructions else base

SYSTEM_PROMPT = get_full_question_prompt("物理", "高中")
KNOWLEDGE_SYSTEM_PROMPT = get_full_knowledge_prompt("物理", "高中")

MAX_RETRY = 2
TIME_OUT = 480
QUESTION_INTERVAL = 1
MAX_FILE_SIZE = 10 * 1024 * 1024

class MultiSubjectProofreadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("多学科题目批量校对工具 v1.6")
        self.root.geometry("1250x780")

        self.task_running = False
        self.task_interrupt = False
        self.paper_list = []
        self.proofread_result = {}
        self.current_level = tk.StringVar(value="高中")
        self.current_subject = tk.StringVar(value="物理")
        self.api_config = self.load_config()
        self.setup_ui()

    def load_config(self):
        """从 .env 读取 API 配置"""
        cfg = {"api_url": "", "api_key": "", "model_name": "", "output_dir": ""}
        if os.path.exists(ENV_FILE):
            try:
                with open(ENV_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            k = k.strip().lower()
                            v = v.strip()
                            if k == 'api_url':
                                cfg['api_url'] = v
                            elif k == 'api_key':
                                cfg['api_key'] = v
                            elif k == 'model_name':
                                cfg['model_name'] = v
            except Exception:
                pass
        return cfg

    def save_config(self):
        """保存 API 配置到 .env"""
        api_url = self.var_api_url.get().strip()
        api_key = self.var_api_key.get().strip()
        model = self.var_model.get().strip()
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            f.write(f"API_URL={api_url}\n")
            f.write(f"API_KEY={api_key}\n")
            f.write(f"MODEL_NAME={model}\n")
        self.api_config = {"api_url": api_url, "api_key": api_key, "model_name": model, "output_dir": self.var_output_dir.get().strip()}
        messagebox.showinfo("提示", "API配置已保存到 .env")

    def reset_config(self):
        self.var_api_url.set("")
        self.var_api_key.set("")
        self.var_model.set("")
        self.var_output_dir.set("")

    def on_level_changed(self, event=None):
        """学段切换时更新学科下拉列表"""
        level = self.current_level.get()
        subjects = subject_config.get_subjects_for_level(level)
        self.subject_combo['values'] = subjects
        if self.current_subject.get() not in subjects:
            self.current_subject.set(subjects[0])
        self.on_subject_changed()

    def on_subject_changed(self, event=None):
        subject = self.current_subject.get()
        level = self.current_level.get()
        global SYSTEM_PROMPT, KNOWLEDGE_SYSTEM_PROMPT
        SYSTEM_PROMPT = get_full_question_prompt(subject, level)
        KNOWLEDGE_SYSTEM_PROMPT = get_full_knowledge_prompt(subject, level)
        tool_count = len(SUBJECT_TOOLS.get(subject, []))
        tool_info = f"，{tool_count}个符号计算工具可用" if tool_count else ""
        self.log(f"学科已切换至：{level}{subject}（提示词已更新{tool_info}）")

    def setup_ui(self):
        frame_api = ttk.LabelFrame(self.root, text="API 配置", padding=10)
        frame_api.pack(fill=tk.X, padx=10, pady=5)

        self.var_api_url = tk.StringVar(value=self.api_config["api_url"])
        self.var_api_key = tk.StringVar(value=self.api_config["api_key"])
        self.var_model = tk.StringVar(value=self.api_config["model_name"])
        self.var_output_dir = tk.StringVar(value=self.api_config.get("output_dir", ""))

        ttk.Label(frame_api, text="接口地址：", width=12).grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_api_url, width=60).grid(row=0, column=1, padx=5, pady=3)
        ttk.Label(frame_api, text="API密钥：", width=12).grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_api_key, width=60, show="*").grid(row=1, column=1, padx=5, pady=3)
        ttk.Label(frame_api, text="模型名称：", width=12).grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_model, width=60).grid(row=2, column=1, padx=5, pady=3)

        ttk.Button(frame_api, text="保存配置", command=self.save_config).grid(row=0, column=2, padx=8)
        ttk.Button(frame_api, text="重置", command=self.reset_config).grid(row=1, column=2, padx=8)

        ttk.Label(frame_api, text="报告输出目录：", width=12).grid(row=3, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_output_dir, width=60).grid(row=3, column=1, padx=5, pady=3)
        ttk.Button(frame_api, text="浏览", command=self.select_output_dir).grid(row=3, column=2, padx=8)

        # 学段+学科选择
        frame_subj = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        frame_subj.pack(fill=tk.X)
        ttk.Label(frame_subj, text="学段：").pack(side=tk.LEFT)
        self.level_combo = ttk.Combobox(frame_subj, textvariable=self.current_level,
                                        values=subject_config.LEVELS, state="readonly", width=6)
        self.level_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.level_combo.bind("<<ComboboxSelected>>", self.on_level_changed)
        ttk.Label(frame_subj, text="校对学科：").pack(side=tk.LEFT)
        self.subject_combo = ttk.Combobox(frame_subj, textvariable=self.current_subject,
                                          values=subject_config.get_subjects_for_level("高中"),
                                          state="readonly", width=8)
        self.subject_combo.pack(side=tk.LEFT, padx=6)
        self.subject_combo.bind("<<ComboboxSelected>>", self.on_subject_changed)

        frame_top = ttk.Frame(self.root, padding=10)
        frame_top.pack(fill=tk.X)

        ttk.Button(frame_top, text="选择试卷根目录", command=self.select_root_dir).grid(row=0, column=0, padx=5)
        ttk.Button(frame_top, text="选择单个试卷目录", command=self.select_single_paper).grid(row=0, column=1, padx=5)
        self.dir_label = ttk.Label(frame_top, text="未选择目录")
        self.dir_label.grid(row=0, column=2, padx=10)

        frame_mid = ttk.Frame(self.root, padding=10)
        frame_mid.pack(fill=tk.BOTH, expand=True)

        frame_left = ttk.Frame(frame_mid)
        frame_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(frame_left, text="待校对试卷清单").pack(anchor=tk.W)
        self.paper_listbox = tk.Listbox(frame_left, height=9)
        self.paper_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        frame_btn = ttk.Frame(frame_left)
        frame_btn.pack(fill=tk.X)
        ttk.Button(frame_btn, text="删除选中", command=self.del_selected).grid(row=0, column=0, padx=2)
        ttk.Button(frame_btn, text="一键清空", command=self.clear_list).grid(row=0, column=1, padx=2)

        frame_right = ttk.Frame(frame_mid)
        frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        ttk.Label(frame_right, text="实时校对日志").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(frame_right, height=9)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)

        frame_bottom = ttk.Frame(self.root, padding=10)
        frame_bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.start_btn = ttk.Button(frame_bottom, text="开始批量校对", command=self.start_proofread)
        self.start_btn.grid(row=0, column=0, padx=5)
        self.stop_btn = ttk.Button(frame_bottom, text="中断任务", command=self.interrupt_task, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)
        ttk.Button(frame_bottom, text="导出校对报告", command=self.export_report).grid(row=0, column=2, padx=5)

    def select_output_dir(self):
        path = filedialog.askdirectory(title="选择校对报告保存目录")
        if path:
            self.var_output_dir.set(path)
            self.log(f"报告输出目录已设置为：{path}")

    def log(self, msg):
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.root.update()

    def select_root_dir(self):
        path = filedialog.askdirectory(title="选择试卷根目录")
        if not path: return
        self.dir_label.config(text=f"根目录：{path}")
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                self.paper_list.append(full_path)
        self.refresh_listbox()
        self.log(f"已加载根目录，共识别 {len(self.paper_list)} 套试卷")

    def select_single_paper(self):
        path = filedialog.askdirectory(title="选择单个试卷文件夹")
        if not path: return
        self.dir_label.config(text=f"单试卷：{path}")
        self.paper_list.append(path)
        self.refresh_listbox()
        self.log(f"已添加试卷：{os.path.basename(path)}")

    def refresh_listbox(self):
        self.paper_listbox.delete(0, tk.END)
        for p in self.paper_list:
            self.paper_listbox.insert(tk.END, os.path.basename(p))

    def del_selected(self):
        idx = self.paper_listbox.curselection()
        if idx:
            self.paper_list.pop(idx[0])
            self.refresh_listbox()

    def clear_list(self):
        self.paper_list.clear()
        self.refresh_listbox()
        self.proofread_result.clear()
        self.log("已清空试卷清单与校对结果")

    def interrupt_task(self):
        if self.task_running:
            self.task_interrupt = True
            self.log("===== 已触发中断，完成当前题目后停止 =====")

    def start_proofread(self):
        api_url = self.var_api_url.get().strip()
        api_key = self.var_api_key.get().strip()
        model = self.var_model.get().strip()
        output_dir = self.var_output_dir.get().strip()

        if not all([api_url, api_key, model]):
            messagebox.showerror("错误", "请先填写并保存完整API配置！")
            return
        if not self.paper_list:
            messagebox.showwarning("提示", "请先添加试卷目录！")
            return
        if self.task_running:
            return

        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                self.log(f"创建输出目录：{output_dir}")
            except Exception as e:
                self.log(f"创建输出目录失败：{e}")
                messagebox.showerror("错误", f"无法创建输出目录：{e}")
                return

        self.task_running = True
        self.task_interrupt = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        t = threading.Thread(target=self.task_loop, daemon=True)
        t.start()

    def call_api_with_retry(self, api_url, api_key, model, md_text, images, q_title, system_prompt, tools=None):
        tool_instances = tools or []
        openai_tools = [_tool_to_openai(t) for t in tool_instances] if tool_instances else None
        err_msg = ""
        chat_url = api_url.rstrip("/")
        if not chat_url.endswith("/chat/completions"):
            chat_url += "/chat/completions"
        for retry in range(MAX_RETRY + 1):
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": f"编号：{q_title}\n内容：\n{md_text}"},
                        *images
                    ]}
                ]
                payload = {
                    "model": model, "messages": messages,
                    "temperature": 0.3, "reasoning_effort": "high"
                }
                if openai_tools:
                    payload["tools"] = openai_tools

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                resp.raise_for_status()
                choice = resp.json()["choices"][0]

                # 处理 tool calls 循环（理科最多5轮，语文最多10轮——网页搜索可能需要多次尝试）
                max_loops = 10 if self.current_subject.get() == "语文" else 5
                loop = 0
                while choice.get("finish_reason") == "tool_calls" or choice["message"].get("tool_calls"):
                    if loop >= max_loops:
                        return f"**工具调用超限：** 模型进行了超过{max_loops}轮工具调用，已中止。"
                    messages.append(choice["message"])
                    for tc in choice["message"]["tool_calls"]:
                        tool_name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        result = _execute_tool(tool_instances, tool_name, args)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result[:4000]
                        })
                        self.log(f"   🔧 {tool_name}({json.dumps(args, ensure_ascii=False)[:120]})")
                    resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                    resp.raise_for_status()
                    choice = resp.json()["choices"][0]
                    loop += 1

                return choice["message"]["content"]
            except Exception as e:
                err_msg = str(e)
                if retry < MAX_RETRY:
                    self.log(f"⚠️ {q_title} 第{retry + 1}次请求超时，正在重试...")
                    time.sleep(2)
        return f"**API调用失败：**\n错误信息：{err_msg}"

    def task_loop(self):
        api_url = self.var_api_url.get().strip()
        api_key = self.var_api_key.get().strip()
        model = self.var_model.get().strip()
        output_dir = self.var_output_dir.get().strip()
        subject = self.current_subject.get()
        subject_tools = SUBJECT_TOOLS.get(subject, [])

        try:
            for paper_path in self.paper_list:
                if self.task_interrupt:
                    break
                paper_name = os.path.basename(paper_path)
                self.log(f"\n>>>>>>>>>> 开始校对试卷：{paper_name} <<<<<<<<<<")

                paper_results = {}

                question_dirs = []
                knowledge_dir = None
                for item in os.listdir(paper_path):
                    full_item = os.path.join(paper_path, item)
                    if not os.path.isdir(full_item):
                        continue
                    if "题" in item or item.startswith("板块"):
                        question_dirs.append(full_item)
                    elif item == "知识":
                        knowledge_dir = full_item

                question_dirs.sort(key=lambda x: int(''.join([c for c in os.path.basename(x) if c.isdigit()]) or 0))

                all_dirs = question_dirs[:]
                if knowledge_dir is not None:
                    all_dirs.append(knowledge_dir)

                for q_dir in all_dirs:
                    if self.task_interrupt:
                        break
                    q_name = os.path.basename(q_dir)
                    is_knowledge = (q_name == "知识")
                    task_type = "知识" if is_knowledge else "题目"

                    self.log(f"正在校对{task_type}：{q_name}（超时上限{TIME_OUT}s）")

                    md_content = ""
                    for f in os.listdir(q_dir):
                        if f.endswith(".md"):
                            with open(os.path.join(q_dir, f), "r", encoding="utf-8") as f_md:
                                md_content = f_md.read()
                            break

                    images_base64 = []
                    img_dir = os.path.join(q_dir, "images")
                    if os.path.exists(img_dir):
                        for img_file in os.listdir(img_dir):
                            if img_file.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                                img_path = os.path.join(img_dir, img_file)
                                file_size = os.path.getsize(img_path)
                                if file_size > MAX_FILE_SIZE:
                                    self.log(f"⚠️ 跳过图片 {img_file}：大小 {file_size / 1024 / 1024:.2f}MB 超过 10MB 限制")
                                    continue
                                try:
                                    with open(img_path, "rb") as f_img:
                                        img_b64 = base64.b64encode(f_img.read()).decode()
                                    ext = img_file.lower().split('.')[-1]
                                    mime = "image/png" if ext == "png" else "image/gif" if ext == "gif" else "image/jpeg"
                                    images_base64.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{mime};base64,{img_b64}"}
                                    })
                                except Exception as e:
                                    self.log(f"❌ 读取图片失败 {img_file}: {str(e)}")

                    prompt_to_use = KNOWLEDGE_SYSTEM_PROMPT if is_knowledge else SYSTEM_PROMPT
                    res = self.call_api_with_retry(api_url, api_key, model, md_content, images_base64, q_name, prompt_to_use, tools=subject_tools)

                    self.proofread_result[q_dir] = res
                    paper_results[q_dir] = res

                    if "API调用失败" in res:
                        err_detail = res.replace("**API调用失败：**\n", "").strip()[:200]
                        self.log(f"❌ {q_name} {task_type}校对失败：{err_detail}")
                    else:
                        json_saved = _save_proofread_json(res, q_dir)
                        if json_saved:
                            self.log(f"✅ {q_name} {task_type}校对完成（JSON 已保存）")
                        else:
                            self.log(f"⚠️ {q_name} {task_type}校对完成（JSON 解析失败，仅保留 Markdown）")

                    time.sleep(QUESTION_INTERVAL)

                if not self.task_interrupt and paper_results:
                    self.auto_export_paper_report(paper_path, paper_results, output_dir)

                # 生成汇总 PDF
                if not self.task_interrupt and paper_results:
                    try:
                        from latex_generator import generate_combined_pdf
                        pdf_dir = os.path.join(os.path.dirname(output_dir) if output_dir else "output", "校对PDF")
                        pdf_path = generate_combined_pdf(paper_path, pdf_dir)
                        if pdf_path:
                            self.log(f"📄 汇总 PDF：{pdf_path}")
                        else:
                            self.log(f"⚠️ 汇总 PDF 生成失败（无可用的校对数据）")
                    except Exception as e:
                        self.log(f"⚠️ 汇总 PDF 生成异常：{e}")

            if self.task_interrupt:
                self.log("\n===== 任务已手动中断 =====")
            else:
                self.log("\n===== 全部题目校对完成 =====")

        except Exception as e:
            self.log(f"❌ 任务异常：{str(e)}")
        finally:
            self.task_running = False
            self.task_interrupt = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def auto_export_paper_report(self, paper_path, paper_results, output_dir):
        if not output_dir:
            self.log("⚠️ 未设置报告输出目录，跳过自动导出")
            return
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                self.log(f"❌ 无法创建输出目录 {output_dir}：{e}")
                return

        paper_name = os.path.basename(paper_path)
        safe_name = "".join(c for c in paper_name if c not in r'\/:*?"<>|')
        report_filename = f"{safe_name}_校对报告.md"
        report_path = os.path.join(output_dir, report_filename)

        report_content = f"# {paper_name} 校对报告\n\n"
        for q_path, content in paper_results.items():
            q_name = os.path.basename(q_path)
            report_content += f"## {q_name}\n{content}\n\n---\n\n"

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            self.log(f"📄 已自动导出试卷报告：{report_path}")
        except Exception as e:
            self.log(f"❌ 自动导出报告失败：{e}")

    def export_report(self):
        if not self.proofread_result:
            messagebox.showwarning("提示", "暂无校对结果！")
            return
        save_path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown文件", "*.md")],
            title="保存校对报告"
        )
        if not save_path:
            return

        subject = self.current_subject.get()
        level = self.current_level.get()
        report = f"# {level}{subject}校对总报告\n\n"
        for q_path, content in self.proofread_result.items():
            paper_name = os.path.basename(os.path.dirname(q_path))
            q_name = os.path.basename(q_path)
            report += f"## {paper_name} - {q_name}\n{content}\n\n---\n\n"

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(report)
        messagebox.showinfo("成功", "校对报告导出完成！")
        self.log(f"📄 校对报告已导出")


if __name__ == "__main__":
    root = tk.Tk()
    app = MultiSubjectProofreadApp(root)
    root.mainloop()
