# 检索引擎工具

`scripts/retrieval_engine/` 按处理阶段拆分为源数据预处理、可复用分词、索引构建、在线检索和离线评测五部分。

## 目录职责

```text
scripts/retrieval_engine/
├─ README.md
├─ source_preprocessing/
│  ├─ README.md
│  ├─ parser.py
│  ├─ folder_catalog.py
│  ├─ excel_writer.py
│  ├─ build_kit_excel.py
│  ├─ build_folder_excel.py
│  ├─ check_kit_coverage.py
│  ├─ build_markdown_corpus.py
│  ├─ requirements.txt
│  └─ data/
│     ├─ kit_coverage_report.json
│     ├─ kit_routing.xlsx
│     └─ folder_mapping.xlsx
├─ tokenizer/
│  ├─ text_preprocessor.py
│  ├─ query_tokenizer.py
│  └─ requirements.txt
├─ indexing/
│  ├─ build_chunk_frequencies.py
│  ├─ build_inverted_index.py
│  └─ data/
│     ├─ markdown_paragraph_corpus.jsonl
│     ├─ chunk_term_frequencies.jsonl
│     ├─ terms_vocab.json
│     └─ index/
│        ├─ inverted.pkl.zst
│        ├─ doc_lengths.pkl.zst
│        ├─ term_stats.pkl.zst
│        ├─ documents.jsonl.zst
│        ├─ exact_terms.json
│        └─ meta.json
├─ retrieval/
│  ├─ exact_query_matcher.py
│  ├─ bm25_engine.py
│  └─ search.py
└─ evaluate/
   ├─ dataset/
   │  └─ dataset.xlsx
   ├─ evaluate_random.py
   ├─ evaluate_document.py
   └─ data/
      ├─ random_20_results.json
      ├─ document_random_20_results.json
      ├─ full_results.json
      ├─ document_full_results.json
      └─ document_vs_chunk_analysis.json
```

- `source_preprocessing/`：解析原始文档、目录和 Kit 路由，生成检查报告、Excel 与 Markdown 章节语料。
- `tokenizer/`：提供索引和检索共同使用的文本归一化与分词能力，不保存索引产物。
- `indexing/`：消费章节语料，生成分片词频、词表和压缩倒排索引。
- `retrieval/`：在线匹配 query 第一类完整词、复用统一预处理并执行 BM25 检索。
- `evaluate/`：从 `dataset/` 读取评测集，对 guides 文档执行随机抽样或全量离线评测，
  并将报告保存到 `data/`。

## 数据流

```text
references Markdown
  → source_preprocessing/build_markdown_corpus.py
  → indexing/data/markdown_paragraph_corpus.jsonl
  → indexing/build_chunk_frequencies.py
  → indexing/data/chunk_term_frequencies.jsonl + terms_vocab.json
  → indexing/build_inverted_index.py
  → indexing/data/index/
```

Kit 路由、目录 Excel 和覆盖报告是独立的源数据检查产物，默认写入 `source_preprocessing/data/`。

## 安装依赖

项目使用 [uv](https://docs.astral.sh/uv/) 创建虚拟环境并安装依赖。
在仓库根目录执行：

```powershell
uv venv
uv pip install -r requirements.txt
```

`uv venv` 默认创建 `.venv`，后续命令继续使用
`.venv\Scripts\python.exe`，确保索引构建、检索和评测使用同一个环境。

## 完整索引构建命令

在仓库根目录依次执行：

```powershell
.venv\Scripts\python.exe source_preprocessing/build_markdown_corpus.py
.venv\Scripts\python.exe indexing/build_chunk_frequencies.py
.venv\Scripts\python.exe indexing/build_inverted_index.py
```

## 源数据检查命令

```powershell
.venv\Scripts\python.exe source_preprocessing/build_kit_excel.py
.venv\Scripts\python.exe source_preprocessing/build_folder_excel.py
.venv\Scripts\python.exe source_preprocessing/check_kit_coverage.py
```

## 在线检索示例

仓库已包含运行检索所需的压缩索引，无需先重新构建语料。

仅检索 `harmonyos-guides/`：

```powershell
.venv\Scripts\python.exe retrieval/search.py `
  "如何使用UIAbility开发应用" `
  --top-k 10 `
  --path-prefix "harmonyos-guides/"
```

输出包含 query 分析、第一类完整词、预处理 token、BM25 分数、路径和命中标题。

如需检索索引中的全部文档，省略 `--path-prefix`：

```powershell
.venv\Scripts\python.exe retrieval/search.py "如何使用Network Kit发起HTTP请求"
```

## Evaluation 示例

评测集位于 `evaluate/dataset/dataset.xlsx`，结果写入 `evaluate/data/`。

### 分片级随机 20 条

```powershell
.venv\Scripts\python.exe evaluate/evaluate_random.py `
  --sample-size 20 `
  --seed 2026 `
  --top-k 10
```

### 文档级随机 20 条

文档分数取同一路径下的最高分片分数：

```powershell
.venv\Scripts\python.exe evaluate/evaluate_document.py `
  --sample-size 20 `
  --seed 2026 `
  --top-k 10
```

### 文档级全量评测

```powershell
.venv\Scripts\python.exe evaluate/evaluate_document.py `
  --sample-size 4057 `
  --top-k 10 `
  --output evaluate/data/document_full_results.json
```

评测输出包含 Hit@1/3/5/10、MRR、每条 query 的完整词匹配、Top10 路径和金标排名。

> 重新构建语料需要将 HarmonyOS 原始 `references/` 文档库放在项目预期位置；
> 只运行检索和已包含数据集的评测不需要原始文档库。
