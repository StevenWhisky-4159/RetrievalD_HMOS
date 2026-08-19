# Indexing

本目录只负责语料词频和倒排索引构建。所有生成数据位于 `data/`。

## 目录

```text
indexing/
├─ build_chunk_frequencies.py
├─ build_inverted_index.py
├─ experiments/
│  ├─ README.md
│  └─ compare_article_exact_matching.py
└─ data/
   ├─ markdown_paragraph_corpus.jsonl
   ├─ terms_vocab.json
   ├─ chunk_term_frequencies.jsonl
   └─ index/
      ├─ inverted.pkl.zst
      ├─ doc_lengths.pkl.zst
      ├─ term_stats.pkl.zst
      ├─ documents.jsonl
      ├─ documents.jsonl.zst
      ├─ exact_terms.json
      └─ meta.json
```

未应用到生产索引的方案统一放在 `experiments/`，目的、结果和决策记录在
`experiments/README.md`。

## 构建顺序

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/source_preprocessing/build_markdown_corpus.py
.venv\Scripts\python.exe scripts/retrieval_engine/indexing/build_chunk_frequencies.py
.venv\Scripts\python.exe scripts/retrieval_engine/indexing/build_inverted_index.py
```

索引和检索统一复用 `../tokenizer/text_preprocessor.py`。

## 精确 term 权重

- 所属子目录中文名：`×4`
- 所属子目录英文名：`×4`
- Markdown 每级标题：`×3`
- 所属子目录之上的全部目录：逐层 `×2`
- 普通预处理 token：`×1`
- 正文中再次出现的第一类完整 term：每次命中 `×1`

正文只匹配当前分片自己的第一类词，允许重叠匹配，不再使用全局第一类词表扫描。
仅长度大于 1（归一化后至少 2 个字符）的第一类词参与正文匹配。
该统计只扫描正文，不重复扫描已经按字段加权的路径和标题。

## BM25 可复用数据

- `doc_lengths.pkl.zst`：
  - `raw`：未应用目录/标题权重的分片 term 总数。
  - `weighted`：应用权重后的 term 总数。
- `term_stats.pkl.zst`：`term -> (df, idf)`。
- `documents.jsonl.zst`：在线检索优先读取的压缩分片元数据。
- `meta.json`：保存 `N`、平均原始/加权长度、`k1`、`b` 和 IDF 公式。

默认 BM25 使用 Posting 中的加权 TF，但长度归一化使用 `raw_length`：

```text
idf = log(1 + (N - df + 0.5) / (df + 0.5))
k1 = 1.5
b = 0.75
```
