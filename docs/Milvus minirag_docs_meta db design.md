# Milvus 数据库设计

**文档级索引（minirag_docs）**

核心定位：作为检索的 “一级筛选器”，快速锁定目标文档范围，减少全库切片检索的性能损耗。

| 字段名                 | 字段类型          | 核心作用                                        |
| :--------------------- | :---------------- | :---------------------------------------------- |
| id                     | Int64（自增主键） | 文档级唯一标识，用于数据管理与关联              |
| file_title             | VarChar(65535)    | 文档名称，用于数据溯源与文档级管理              |
| origin_file_url        | VarChar(65535)    | 上传原始文档链接（Minio 路径）                  |
| final_markdown_url     | VarChar(65535)    | 转 markdown、图片语法替换后的 markdown 文档链接 |
| chunks_url             | VarChar(65535)    | 经过切分过后的 chunks.json 文件 url             |
| docs_keywords          | VarChar(65535)    | 文档关键字，用英文逗号分隔                      |
| docs_abstract          | VarChar(65535)    | 文档摘要                                        |
| keywords_sparse_vector | SparseFloatVector | 文档关键字的稀疏向量                            |
| keywords_dense_vector  | FloatVector(1024) | 文档关键字的稠密向量                            |
| abstract_dense_vector  | FloatVector(1024) | 文档摘要的稠密向量                              |
| abstract_sparse_vector | SparseFloatVector | 文档摘要的稀疏向量                              |

**切片级索引（minirag_chunks）**

核心定位：检索的 “精准匹配层”，存储细粒度语义切片，直接为大模型提供上下文证据。

| 字段名                | 字段类型          | 核心作用                                           |
| :-------------------- | :---------------- | :------------------------------------------------- |
| id                    | Int64（自增主键） | 切片全局唯一标识，作为数据操作主键                 |
| doc_id                | Int64             | 指向 minirag_docs 中的 id, 对应chunk来自哪篇文档   |
| file_title            | VarChar(65535)    | 对应文档的 file_title                              |
| chunk_index           | INT64             | 当前 chunk 在文档 chunks 中的序号，从 0 开始       |
| chunk_content         | VarChar(65535)    | 切片文本内容（含标题层级），是向量编码的核心数据源 |
| content_dense_vector  | FloatVector(1024) | 切片语义向量，适配模糊语义检索，提升上下文匹配度   |
| content_sparse_vector | SparseFloatVector | 切片关键词向量，适配精确检索，提升术语匹配精度     |
