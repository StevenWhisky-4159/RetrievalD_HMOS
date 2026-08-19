# Tokenizer

本目录只负责索引与检索共用的文本预处理，不包含索引构建代码或索引数据。

## 文件

- `text_preprocessor.py`：中英文、特殊标识符、标点、空白和停用词处理。
- `query_tokenizer.py`：检索 query 的命令行入口。
- `requirements.txt`：运行依赖。

## 处理流程

1. Unicode NFKC 归一化。
2. 提前识别点分 API、CamelCase、snake_case、连字符、`C++` 等特殊词。
3. 保留完整特殊词，并补充点号、下划线、连字符和 CamelCase 子词。
4. 剩余文本清除空白、标点和符号后交给 jieba。
5. 统一英文小写并删除停用词、纯数字和无意义单字符英文。

## Query

```powershell
.venv\Scripts\python.exe scripts/retrieval_engine/tokenizer/query_tokenizer.py "使用@ohos.app.ability.UIAbility开发应用"
```

代码复用：

```python
from tokenizer.text_preprocessor import TextPreprocessor

tokens = TextPreprocessor().tokenize_to_list(query)
```
