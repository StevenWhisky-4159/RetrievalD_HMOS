# Evaluate

本目录提供离线检索评测，使用 `../indexing/data/index/` 中已有索引。评测数据集与
结果报告分开存放；结果写入 `data/`。

- `evaluate_random.py`：分片级排名。
- `evaluate_document.py`：按 Markdown 路径聚合，支持三种文档评分模式。
- `evaluate_query_code.py`：读取 `user_prompt + markers`，批量执行 query +
  code patterns 检索。
- `document_scoring_sample_400_analysis.md`：三种文档评分模式的 Sample 400
  对比分析。

## 文档评分 Sample 400

固定使用 `dataset/sample_400.xlsx`、随机种子 2026 和 Top 10：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_document.py `
  --dataset scripts/retrieval_engine/evaluate/dataset/sample_400.xlsx `
  --sample-size 400 --seed 2026 --top-k 10 `
  --document-score-mode max `
  --output scripts/retrieval_engine/evaluate/data/document_sample_400_max.json

.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_document.py `
  --dataset scripts/retrieval_engine/evaluate/dataset/sample_400.xlsx `
  --sample-size 400 --seed 2026 --top-k 10 `
  --document-score-mode weighted --max-score-weight 0.5 `
  --output scripts/retrieval_engine/evaluate/data/document_sample_400_weighted.json

.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_document.py `
  --dataset scripts/retrieval_engine/evaluate/dataset/sample_400.xlsx `
  --sample-size 400 --seed 2026 --top-k 10 `
  --document-score-mode max_plus_sum `
  --output scripts/retrieval_engine/evaluate/data/document_sample_400_max_plus_sum.json
```

总体上 `weighted(0.5/0.5)` 最优：Hit@1 为 69.25%，MRR 为 0.8115；
`max` 的 Hit@1 为 68.00%，MRR 为 0.7969；`max_plus_sum` 的 Hit@1 为
66.25%，MRR 为 0.7888。完整配对分析、bootstrap 区间、文档分片数分层和
典型样例见 [`document_scoring_sample_400_analysis.md`](document_scoring_sample_400_analysis.md)。

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

文档级结果默认使用最高分片代表文档分数。切换为最高分片与全部分片平均分
各占 `0.5`：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_query_code.py `
  --document-score-mode weighted `
  --max-score-weight 0.5
```

也可使用最高分片加全部分片得分和的模式：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/evaluate/evaluate_query_code.py `
  --document-score-mode max_plus_sum
```

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
