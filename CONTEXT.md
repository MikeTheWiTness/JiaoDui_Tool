# 校对 v1.6 — K-12 Multi-Subject Content Proofreading Pipeline

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

**校对报告** (Proofreading Report):
The LLM's output after reviewing a question — currently a narrative Markdown file, transitioning to structured JSON + LaTeX PDF.
_Avoid_: 审查结果, 审核报告

**修改项** (Correction Item):
A single correction produced by the LLM, containing the original text, corrected text, and reason. Three types: `text`, `rewrite`, `region`.
_Avoid_: 错误点, 问题点

**学段** (Level):
K-12 tier — 小学 (elementary), 初中 (junior high), 高中 (senior high).
_Avoid_: 年级, 阶段

**拆分模式** (Split Mode):
How a lecture is divided — `title` mode (bold problem markers like `**例1**`) or `section` mode (by `##` headers).

## Flagged Ambiguities

- **校对报告 vs 校对数据**: "Report" now refers specifically to the PDF output; the LLM's raw structured output is called "校对数据 (proofreading data / JSON data)." The old `_校对报告.md` remains as a human-readable fallback.

## Example Dialogue

> **Dev**: 这道题的校对数据里有三个修改项——一个 text 类型改错别字，一个 rewrite 类型重写整段解析，还有一个 region 类型标了配图有问题。
> **Domain Expert**: text 和 rewrite 好处理，在原题 .md 里直接定位标记就行。region 那个，左栏得把整张图用红框标出来。
> **Dev**: 然后跑 LaTeX 编译成 PDF，paracol 双栏，左栏原文加红标记，右栏修改建议。
> **Domain Expert**: 对，最后 PDF 放 `output/校对PDF/`，原来的 `_校对报告.md` 继续保留不动。
