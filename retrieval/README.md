# Retrieval

BM25 检索入口，复用 `tokenizer/` 的 query 预处理和 `indexing/data/index/` 的预计算数据。

## Query 流程

1. 使用 `exact_terms.json` 判断 query 是否包含长度大于 2 的第一类完整词。
2. 记录全部命中的第一类词及出现次数。
3. 使用 `TextPreprocessor` 处理英文、特殊标识符、标点、空白和停用词，再进行 jieba 中文分词。
4. 合并第一类完整词和普通 token。
5. 使用 Posting 中的加权 TF、`raw_length`、预计算 IDF 执行 BM25。

BM25：

```text
score = idf × tf × (k1 + 1)
        / (tf + k1 × (1 - b + b × dl / avgdl))
        × query_tf
```

## 单条检索

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/retrieval/search.py "如何使用UIAbility开发应用" --top-k 10
```

仅检索 guides：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/retrieval/search.py "如何使用UIAbility开发应用" `
  --path-prefix "harmonyos-guides/"
```
