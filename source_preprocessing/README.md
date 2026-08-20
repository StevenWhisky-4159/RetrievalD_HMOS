# Source Preprocessing

本目录负责读取 HarmonyOS 原始 Markdown 文档与路由元数据，并生成供检查、分析或索引使用的结构化数据。脚本均可在仓库根目录直接运行。

## 文件职责

- `parser.py`：解析 Kit 路由表、目录中英文名称。
- `folder_catalog.py`：扫描并对齐指南、basic skill 与 API 目录。
- `excel_writer.py`：提供 Excel 写出能力。
- `build_kit_excel.py`：由 `kit-routing.md` 生成 Kit 路由表。
- `build_folder_excel.py`：由实际目录生成完整目录对照表。
- `check_kit_coverage.py`：检查路由与文档目录覆盖情况。
- `build_markdown_corpus.py`：将 Markdown 按章节转换为一一对应的文本语料和代码语料。
- `requirements.txt`：源数据解析与 Excel 写出的运行依赖。
- `data/`：保存覆盖报告和 Excel 等预处理产物；索引语料除外。

## 命令

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/build_kit_excel.py
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/build_folder_excel.py
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/check_kit_coverage.py
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/build_markdown_corpus.py
```

默认输出：

- `data/kit_routing.xlsx`
- `data/folder_mapping.xlsx`
- `data/kit_coverage_report.json`
- `../indexing/data/markdown_paragraph_corpus.jsonl`
- `../indexing/data/markdown_code_corpus.jsonl`

文本语料使用连续的 `chunk_id`，代码语料使用独立的 `code_chunk_id`，并通过
可为空的 `text_chunk_id` 关联同章节文本分片。`block_code` 保存
fenced/indented 代码及其 `style`、`info`，`inline_code` 保存行内代码。
块级代码不会写入文本正文，也不会参与文本分词与索引；行内代码保留在正文中
参与普通分词，同时在代码语料中保留原始内容。纯块级代码章节只存在于代码语料中。
