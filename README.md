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
│        ├─ documents.jsonl
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

```powershell
.venv\Scripts\python.exe -m pip install -r scripts/retrieval_engine/requirements.txt
```

## 完整索引构建命令

在仓库根目录依次执行：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/build_markdown_corpus.py
.venv\Scripts\python.exe scripts/retrieval_engine/indexing/build_chunk_frequencies.py
.venv\Scripts\python.exe scripts/retrieval_engine/indexing/build_inverted_index.py
```

## 源数据检查命令

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/build_kit_excel.py
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/build_folder_excel.py
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/check_kit_coverage.py
```
