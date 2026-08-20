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
│     ├─ markdown_code_corpus.jsonl
│     ├─ chunk_term_frequencies.jsonl
│     ├─ terms_vocab.json
│     └─ index/
│        ├─ inverted.pkl.zst
│        ├─ doc_lengths.pkl.zst
│        ├─ term_stats.pkl.zst
│        ├─ chunk_mappings.pkl.zst
│        ├─ documents.jsonl.zst
│        ├─ exact_terms.json
│        └─ meta.json
├─ retrieval/
│  ├─ exact_query_matcher.py
│  ├─ mappers.py
│  ├─ bm25_engine.py
│  └─ search.py
└─ evaluate/
   ├─ dataset/
   │  ├─ dataset.xlsx
   │  └─ sample_400.xlsx
   ├─ evaluate_random.py
   ├─ evaluate_document.py
   ├─ evaluate_query_code.py
   ├─ document_scoring_sample_400_analysis.md
   └─ data/
      ├─ random_20_results.json
      ├─ document_random_20_results.json
      ├─ document_sample_400_max.json
      ├─ document_sample_400_weighted.json
      ├─ document_sample_400_max_plus_sum.json
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
    + indexing/data/markdown_code_corpus.jsonl（独立代码分片）
  → indexing/build_chunk_frequencies.py
  → indexing/data/chunk_term_frequencies.jsonl + terms_vocab.json
  → indexing/build_inverted_index.py
  → indexing/data/index/
```

Kit 路由、目录 Excel 和覆盖报告是独立的源数据检查产物，默认写入 `source_preprocessing/data/`。
代码语料通过可为空的 `text_chunk_id` 关联文本分片。块级代码不进入文本分词与
BM25 索引；行内代码保留在正文中参与普通分词，同时也写入代码语料供独立代码
检索使用。

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

仅检索 guides 板块：

```powershell
.venv\Scripts\python.exe retrieval/search.py `
  "如何使用UIAbility开发应用" `
  --top-k 10 `
  --scope guides
```

输出包含 query 分析、第一类完整词、预处理 token、BM25 分数、路径和命中标题。

如需检索索引中的全部文档，省略 `--scope` 和 `--path-prefix`：

```powershell
.venv\Scripts\python.exe retrieval/search.py "如何使用Network Kit发起HTTP请求"
```

返回按 Markdown 路径聚合的文档级结果：

```powershell
.venv\Scripts\python.exe retrieval/search.py `
  "如何使用UIAbility开发应用" `
  --scope guides `
  --granularity document
```

文档得分默认取最高分片。使用最高分片和全部分片平均分各占 `0.5` 的加权模式：

```powershell
.venv\Scripts\python.exe retrieval/search.py `
  "如何使用UIAbility开发应用" `
  --scope guides `
  --granularity document `
  --document-score-mode weighted `
  --max-score-weight 0.5
```

使用“最高分片 + 全部分片得分和，再除以分片数 + 1”的模式：

```powershell
.venv\Scripts\python.exe retrieval/search.py `
  "如何使用UIAbility开发应用" `
  --scope guides `
  --granularity document `
  --document-score-mode max_plus_sum
```

使用代码正则动态增加命中分片的中文目录 term TF：

```powershell
.venv\Scripts\python.exe retrieval/search.py `
  "基于RAG框架实现邮件智能问答" `
  --scope best-practices `
  --code-pattern "createRagSession"
```

`--code-pattern` 可以重复传入，并匹配块级和行内代码。每个 pattern 按命中的
代码单元数量累加 TF；query 不含中文目录 term 时，只为代码实际命中的分片
注入该 term，TF 等于命中数。预计算 IDF 和 `raw_length` 保持不变。

## Evaluation 示例

评测集位于 `evaluate/dataset/dataset.xlsx`，结果写入 `evaluate/data/`。

### 文档评分 Sample 400

`evaluate/dataset/sample_400.xlsx` 使用随机种子 2026 从 4057 条数据中抽取。
三种模式的结果和分析位于：

- `evaluate/data/document_sample_400_max.json`
- `evaluate/data/document_sample_400_weighted.json`
- `evaluate/data/document_sample_400_max_plus_sum.json`
- [`evaluate/document_scoring_sample_400_analysis.md`](evaluate/document_scoring_sample_400_analysis.md)

当前样本中 `weighted(0.5/0.5)` 指标最好，但包含平均分的模式会产生文档长度
偏置；切换默认模式前建议运行全量数据或多个随机种子。

### Query + code patterns 样例

读取 `scripts/code_tests/query_code_example.xlsx`：

```powershell
.venv\Scripts\python.exe evaluate/evaluate_query_code.py --top-k 10
```

默认按 Markdown 文档聚合，结果写入
`evaluate/data/query_code_example_results.json`。传入
`--granularity chunk` 可切换为分片级检索。检索范围通过
`--scope all|basic-skills|guides` 选择，默认 `all`。

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
