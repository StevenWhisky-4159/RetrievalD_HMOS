# Retrieval

BM25 检索入口，复用 `tokenizer/` 的 query 预处理和 `indexing/data/index/` 的预计算数据。

## Query 流程

1. 使用 `exact_terms.json` 判断 query 是否包含长度大于 2 的第一类完整词。
2. 记录全部命中的第一类词及出现次数。
3. 使用 `TextPreprocessor` 处理英文、特殊标识符、标点、空白和停用词，再进行 jieba 中文分词。
4. 合并第一类完整词和普通 token。
5. 板块映射器将 `scope` 或路径前缀解析为候选分片，在 BM25 计算前过滤。
6. 可选代码正则扫描候选分片的块级和行内代码；每个 pattern 每命中一个代码
   单元，就为该分片的“所属子目录中文”term 增加 `1` TF。
7. 使用 Posting 中的加权 TF、`raw_length`、预计算 IDF 执行 BM25。
8. 文档级检索通过分片到文档映射聚合同一 Markdown 文档的命中分片。

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

仅检索 guides 板块：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/retrieval/search.py "如何使用UIAbility开发应用" `
  --scope guides
```

仅检索 basic skills 并返回文档级结果：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/retrieval/search.py "如何使用UIAbility开发应用" `
  --scope basic-skills `
  --granularity document
```

支持 `all`、`guides`、`basic-skills`、`references`、`faqs`、`releases` 和
`best-practices`。`--path-prefix` 保留用于兼容和更细路径范围，但不能与
`--scope` 同时使用。范围过滤复用索引中的 `chunk_mappings.pkl.zst`，不会在
每次查询后扫描全部结果做路径过滤。

## 代码 pattern

`--code-pattern` 可重复传入，每个值均按 Python 正则表达式解析：

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/retrieval/search.py `
  "基于RAG框架实现邮件智能问答" `
  --scope best-practices `
  --code-pattern "createRagSession" `
  --code-pattern "releaseRagSession"
```

同一个 pattern 在同一分片命中多个块级或行内代码时，按命中的代码单元数量
累加；多个 pattern 分别计数。若 query 已包含“所属子目录中文”term，命中数
加到该 term 的索引 TF；若 query 不包含，则只对代码实际命中的分片增加该
term，TF 直接等于代码命中数，query TF 取 `1`。预计算 IDF 和 `raw_length`
保持不变。
