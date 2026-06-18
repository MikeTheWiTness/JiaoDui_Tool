# 校对 v1.7 — K-12 Multi-Subject Content Proofreading Pipeline

A three-stage pipeline (Convert → Split → Proofread) for K-12 educational content across 24 subject-level combinations.

## Language

**讲义** (Lecture):
Teaching material that gets split into individual questions or sections for proofreading.
_Avoid_: 课件, 教案

**题目** (Question/Problem):
A single problem unit extracted from a lecture — includes question text, answer, and optional images.
_Avoid_: 试题, 考题

**板块** (Section):
A coherent teaching unit split by `##` headers in English lectures (section mode). Each section becomes one proofreading unit.
_Avoid_: 章节, 模块

**知识** (Knowledge):
Non-problem supplementary content (formulas, concept summaries) extracted during title-mode splitting.
_Avoid_: 知识点总结, 附录

**校对回复** (Proofread Response):
The LLM's raw Markdown output after reviewing a question or section — saved as `_校对报告.md`.
_Avoid_: 审查结果, 审核报告

**校对数据** (Proofread Data):
Structured JSON extracted from the LLM's Markdown response by `_parse_proofread_md()` — saved as `_校对数据.json`. Contains typed correction items.
_Avoid_: 校对报告, 校对结果

**校对报告** (Proofread Report):
The final rendered PDF report with paracol two-column layout (left: original + red markers, right: corrections). Also used for the per-exam summary `.md` report.
_Avoid_: 审查报告, 审核报告

**修改项** (Correction Item):
A single correction produced by the LLM, containing the original text, corrected text, and reason. Three types: `text`, `rewrite`, `region`.
_Avoid_: 错误点, 问题点

**学段** (Level):
K-12 tier — 小学 (elementary), 初中 (junior high), 高中 (senior high).
_Avoid_: 年级, 阶段

**拆分模式** (Split Mode):
How a lecture is divided — `title` mode (bold problem markers like `**例1**`) or `section` mode (by `##` headers).

## Flagged Ambiguities

- **校对回复 vs 校对数据 vs 校对报告**: The LLM's raw Markdown output is the **校对回复** (`_校对报告.md`). Its parsed JSON form is **校对数据** (`_校对数据.json`). The rendered PDF is the **校对报告**. The old `_校对报告.md` filename is preserved for backward compatibility but its content is the 校对回复, not the final report.

## Example Dialogue

> **Dev**: 这道题的校对数据里有三个修改项——一个 text 类型改错别字，一个 rewrite 类型重写整段解析，还有一个 region 类型标了配图有问题。
> **Domain Expert**: text 和 rewrite 好处理，在原题 .md 里直接定位标记就行。region 那个，左栏得把整张图用红框标出来。
> **Dev**: 然后跑 LaTeX 编译成 PDF 校对报告，paracol 双栏，左栏原文加红标记，右栏修改建议。
> **Domain Expert**: 对，最后 PDF 放 `output/校对PDF/`，原来的校对回复 `_校对报告.md` 和校对数据 `_校对数据.json` 继续保留不动。
