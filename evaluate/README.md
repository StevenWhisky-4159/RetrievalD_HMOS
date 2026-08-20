# Evaluate

本目录提供离线检索评测，使用 `../indexing/data/index/` 中已有索引。评测数据集与
结果报告分开存放；结果写入 `data/`。

- `evaluate_random.py`：分片级排名。
- `evaluate_document.py`：按 Markdown 路径聚合，文档得分取最高分片得分。
- `evaluate_query_code.py`：读取 `user_prompt + markers`，批量执行 query +
  code patterns 检索。

## Query + code patterns

默认读取 `scripts/code_tests/query_code_example.xlsx` 的 `Sheet1`。`markers`
必须是由正则字符串组成的 JSON 数组：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_query_code.py `
  --top-k 10
```

默认执行全量文档级检索，结果写入 `data/query_code_example_results.json`。
检索范围参数为：

- `--scope all`：全量检索，也是省略参数时的默认行为。
- `--scope basic-skills`（或 `basic-skill`）：只检索 basic skill。
- `--scope guides`：只检索 guides。

传入 `--granularity chunk` 可改为分片级结果。该样例没有金标路径，因此报告
记录检索结果和代码命中统计，不计算 Hit 或 MRR。

## 随机 20 条评测

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_random.py `
  --sample-size 20 `
  --seed 2026 `
  --top-k 10
```

结果默认写入 `data/random_20_results.json`。

## 文档级随机 20 条评测

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_document.py `
  --sample-size 20 `
  --seed 2026 `
  --top-k 10
```

结果默认写入 `data/document_random_20_results.json`。Top10 中每个路径最多出现一次，
并记录该文档的最高分分片标题。

## 文档级全量评测

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_document.py `
  --sample-size 4057 `
  --top-k 10 `
  --output scripts/retrieval_engine/evaluate/data/document_full_results.json
```

分片级与文档级全量对比分析保存在：

`data/document_vs_chunk_analysis.json`

## 全量评测

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_random.py `
  --sample-size 1000000000 `
  --top-k 10 `
  --output scripts/retrieval_engine/evaluate/data/full_results.json
```

评测会取 `--sample-size` 与可用数据量中的较小值，因此上述命令覆盖全部有效行。
结果写入 `data/full_results.json`。两个命令默认使用
`--path-prefix "harmonyos-guides/"`，只对 guides 文档排名。
