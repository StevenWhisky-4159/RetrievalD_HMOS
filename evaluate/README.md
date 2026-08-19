# Evaluate

本目录提供仅针对 `harmonyos-guides/` 文档的离线检索评测。默认读取
`dataset/dataset.xlsx`，并使用 `../indexing/data/index/` 中已有索引。评测数据集与
结果报告分开存放；结果仍写入 `data/`。

- `evaluate_random.py`：分片级排名。
- `evaluate_document.py`：按 Markdown 路径聚合，文档得分取最高分片得分。

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
