from typing import NotRequired, TypedDict
from common.model.qwen_embedding import HybridVector
from common.config.app_config import APP_CONFIG
from common.model import EMBEDDING
from utils.logging_utils import logger
from utils.net_utils import probe_tcp
from common.config.env_config import ENV_CONFIG
from pymilvus import AnnSearchRequest, DataType, MilvusClient, WeightedRanker


def _escape_milvus_str(value: str) -> str:
    """转义 Milvus filter 表达式字符串字面量中的双引号与反斜杠。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


# minirag_docs 表相关类型定义
class MilvusDocsField:
    ID = "id"
    TASK_ID = "task_id"
    FILE_TITLE = "file_title"
    ORIGIN_FILE_URL = "origin_file_url"
    FINAL_MARKDOWN_URL = "final_markdown_url"
    CHUNKS_URL = "chunks_url"
    DOCS_KEYWORDS = "docs_keywords"
    DOCS_ABSTRACT = "docs_abstract"
    KEYWORDS_SPARSE_VECTOR = "keywords_sparse_vector"
    ABSTRACT_DENSE_VECTOR = "abstract_dense_vector"


class MilvusDocsIndex:
    ABSTRACT_DENSE_VECTOR_INDEX = "abstract_dense_index"
    KEYWORDS_SPARSE_VECTOR_INDEX = "keywords_sparse_index"


class MilvusDocsItem(TypedDict):
    id: NotRequired[int]  # auto_id 自增主键, 插入时不传
    task_id: str
    file_title: str
    origin_file_url: str
    final_markdown_url: str
    chunks_url: str
    docs_keywords: str
    docs_abstract: str
    keywords_sparse_vector: dict[int, float]
    abstract_dense_vector: list[float]


# minirag_chunks 表相关类型定义
class MilvusChunksField:
    ID = "id"
    DOC_ID = "doc_id"
    FILE_TITLE = "file_title"
    CHUNK_INDEX = "chunk_index"
    CHUNK_CONTENT = "chunk_content"
    CONTENT_DENSE_VECTOR = "content_dense_vector"
    CONTENT_SPARSE_VECTOR = "content_sparse_vector"


class MilvusChunksIndex:
    CONTENT_DENSE_VECTOR_INDEX = "content_dense_index"
    CONTENT_SPARSE_VECTOR_INDEX = "content_sparse_index"


class MilvusChunksItem(TypedDict):
    id: NotRequired[int]  # auto_id 自增主键, 插入时不传
    doc_id: int
    file_title: str
    chunk_index: int
    chunk_content: str
    content_dense_vector: list[float]
    content_sparse_vector: dict[int, float]


class MilvusDocsRecall(TypedDict):
    id: int
    score: float

    # Milvus 文档级混合检索输出字段
    # 对应 hybrid_search_docs 中 output_fields
    file_title: str
    docs_abstract: str


class MilvusChunksRecall(TypedDict):
    id: int
    score: float

    # Milvus chunks 混合检索输出字段
    # 对应 hybrid_search_chunks 中 output_fields
    doc_id: int
    file_title: str
    chunk_index: int
    chunk_content: str


class HybridSearchRecall(TypedDict):
    id: int
    distance: float
    entity: dict  # 取决于 output_field


class MiniRagMilvusClient(MilvusClient):
    def __init__(self):
        super().__init__(uri=ENV_CONFIG.milvus.endpoint)

    def check_health(self) -> None:
        """连通性自检: TCP 可达 + 服务端能返回版本号。"""
        probe_tcp(ENV_CONFIG.milvus.endpoint)
        version = self.get_server_version()
        logger.success(
            f"Milvus 连接成功 ({ENV_CONFIG.milvus.endpoint}), 服务端版本: {version}"
        )

    def hybrid_search_docs(
        self,
        texts: list[str],
        limit: int = APP_CONFIG.docs_recall_limit,
    ) -> list[list[MilvusDocsRecall]] | None:
        """文档级一级召回: 摘要稠密 + 关键词稀疏混合检索。

        texts 为查询侧识别的检索线索 (如询问主体) 列表,
        外层返回 list 对应 len(texts), 内层为各查询的 top-k 命中:

            [
                [  # texts[0] 的命中
                    {
                        "id": 469734951640943804, -> entity 主键ID
                        "score": 0.8866561651229858, -> 最终融合得分
                        "file_title": ...,
                        "docs_abstract": ...,
                    },
                    ...
                ],
                ...
            ]

        搜索失败时返回 None。
        """
        collection_name = ENV_CONFIG.milvus.collection_docs
        output_fields = [
            MilvusDocsField.FILE_TITLE,
            MilvusDocsField.DOCS_ABSTRACT,
        ]

        texts_vectors = EMBEDDING.embed_query_hybrid(texts)
        # 摘要匹配用稠密分量, 关键词匹配用稀疏分量
        dense_vectors = [vec["dense"] for vec in texts_vectors]
        sparse_vectors = [vec["sparse"] for vec in texts_vectors]

        hits = self._minirag_hybrid_search(
            collection_name=collection_name,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            dense_field=MilvusDocsField.ABSTRACT_DENSE_VECTOR,
            sparse_field=MilvusDocsField.KEYWORDS_SPARSE_VECTOR,
            output_fields=output_fields,
            weight=APP_CONFIG.docs_hybrid_weight,
            limit=limit,
        )

        return self._convert_hit_results(hits)

    def hybrid_search_chunks(
        self,
        query_text: list[str],
        doc_ids: list[int] = None,
        limit: int = APP_CONFIG.chunks_recall_limit,
    ) -> list[list[MilvusChunksRecall]] | None:
        """切片级二级召回, 检索范围严格限定在 doc_ids 对应的确认文档内。

        doc_ids 为空时不加过滤 (全库检索, 调用侧应保证只在确认文档
        存在时进入本路径)。
        """
        collection_name = ENV_CONFIG.milvus.collection_chunks
        output_fields = [
            MilvusChunksField.DOC_ID,
            MilvusChunksField.FILE_TITLE,
            MilvusChunksField.CHUNK_INDEX,
            MilvusChunksField.CHUNK_CONTENT,
        ]

        vectors: list[HybridVector] = EMBEDDING.embed_query_hybrid(query_text)
        dense_vector = [vec["dense"] for vec in vectors]
        sparse_vector = [vec["sparse"] for vec in vectors]

        filter_expr = None
        if doc_ids:
            filter_expr = f"{MilvusChunksField.DOC_ID} in {doc_ids}"

        hits = self._minirag_hybrid_search(
            collection_name=collection_name,
            dense_vectors=dense_vector,
            sparse_vectors=sparse_vector,
            dense_field=MilvusChunksField.CONTENT_DENSE_VECTOR,
            sparse_field=MilvusChunksField.CONTENT_SPARSE_VECTOR,
            limit=limit,
            weight=APP_CONFIG.chunks_hybrid_weight,
            filter=filter_expr,
            output_fields=output_fields,
        )

        return self._convert_hit_results(hits)

    # Milvus 混合搜索 (稠密向量 + 稀疏向量)
    # https://milvus.io/docs/multi-vector-search.md
    # https://milvus.io/api-reference/pymilvus/v3.0.x/MilvusClient/Vector/hybrid_search.md
    def _minirag_hybrid_search(
        self,
        collection_name: str,
        dense_vectors: list[list[float]],
        sparse_vectors: list[dict[int, float]],
        dense_field: str,
        sparse_field: str,
        limit: int,
        weight: tuple[float, float],
        filter: str | None = None,
        output_fields: list[str] = ["*"],
    ) -> list[list[HybridSearchRecall]] | None:
        """稠密 + 稀疏混合搜索, 支持批量查询 (nq > 1)。

        dense_field / sparse_field 由调用方传入, 两表共用同一实现
        (docs 表匹配 abstract_dense + keywords_sparse,
        chunks 表匹配 content_dense + content_sparse)。

        返回 list[list[HybridSearchHits]]
        外层长度 = 查询向量个数 (nq),
        内层长度 = top-k 命中数 (limit),
        [
            [  # 第一个查询向量的命中
                HybridSearchHits,
                HybridSearchHits,
                ...
            ],
            [  # 第二个查询向量的命中
                ...
            ],
            ...
        ]
        """
        if not dense_vectors:
            raise ValueError("dense_vectors 不能为空")
        if len(dense_vectors) != len(sparse_vectors):
            raise ValueError(
                "dense_vectors 与 sparse_vectors 的查询向量数量必须一致, "
                f"got {len(dense_vectors)} vs {len(sparse_vectors)}"
            )

        # 1. 创建多个 AnnSearchRequest 对象
        # https://milvus.io/docs/multi-vector-search.md#Step-1-Create-multiple-AnnSearchRequest-instances
        # AnnSearchRequest.data 类型为 List[List[float]], 每个请求可包含多个查询向量 (nq > 1)。
        # 稠密/稀疏两侧的查询向量数量必须一致, 否则服务端会报错。
        dense_req = AnnSearchRequest(
            data=dense_vectors,
            anns_field=dense_field,
            param={
                "metric_type": "COSINE",
            },  # 更多 ANN 参数设置也是在这个字典里
            limit=limit,  # 每个请求返回的最大结果数
            filter=filter,  # 可选的过滤条件
        )
        sparse_req = AnnSearchRequest(
            data=sparse_vectors,
            anns_field=sparse_field,
            param={
                "metric_type": "IP",
            },
            limit=limit,
            filter=filter,
        )
        reqs = [dense_req, sparse_req]

        # 2. 定义 Ranker 策略
        # https://milvus.io/docs/multi-vector-search.md#Step-2-Configure-a-reranking-strategy
        # https://milvus.io/docs/weighted-ranker.md#Create-a-Weighted-Ranker
        dense_weight, sparse_weight = weight
        ranker = WeightedRanker(dense_weight, sparse_weight)

        try:
            res = super().hybrid_search(
                collection_name,
                reqs,
                ranker,
                limit,
                output_fields,
                timeout=APP_CONFIG.milvus_search_timeout,
            )
        except Exception as e:
            logger.error(f"MiniRag hybrid search failed: {e}")
            return None

        return res

    def _convert_hit_results(
        self,
        hits: list[list[HybridSearchRecall]] | None,
    ) -> list[list[dict]] | None:
        """
        处理 Milvus 原生 hybrid_search 结果的外层列表嵌套。

        外层 list 对应 nq 个查询向量, 内层 list 对应每个查询的 top-k 命中,
        单个命中的转换统一交由 _convert_hit 处理。

        示例 (docs 场景, 2 个查询向量):
        输入:
        [
            [
                {"id": 1, "distance": 0.9, "entity": {"file_title": "A"}},
                {"id": 2, "distance": 0.8, "entity": {"file_title": "B"}},
            ],
            [
                {"id": 3, "distance": 0.7, "entity": {"file_title": "C"}},
            ],
        ]
        输出:
        [
            [
                {"id": 1, "score": 0.9, "file_title": "A"},
                {"id": 2, "score": 0.8, "file_title": "B"},
            ],
            [
                {"id": 3, "score": 0.7, "file_title": "C"},
            ],
        ]
        """
        if hits is None:
            return None

        return [[self._convert_hit(hit) for hit in hit_group] for hit_group in hits]

    def _convert_hit(self, hit: HybridSearchRecall) -> dict:
        """
        将单个 HybridSearchHits 转换为对外的 Hit 容器。

        对外统一暴露 {id, score, ...entity 字段} 结构, 不再泄漏 HybridSearchHits:
        1. 顶层 distance 统一重命名为 score
        2. entity 内的输出字段拍平到顶层
        3. 主键 id 从顶层合并进结果 (entity 中不含主键 id)

        示例:
        输入 (HybridSearchHits):
        {
            "id": 469734951640943804,
            "distance": 0.8866561651229858,
            "entity": {"file_title": "万用表RS-12的使用", ...},
        }
        输出 (MilvusDocsRecall):
        {
            "id": 469734951640943804,
            "score": 0.8866561651229858,
            "file_title": "万用表RS-12的使用",
            ...
        }
        """
        return {
            **hit.get("entity", {}),
            "id": hit.get("id"),
            "score": hit.get("distance", 0.0),
        }

    # ------------------------------------------------------------------ #
    # 文档级增删查辅助 (供导入链路 node_document_embedding 使用)
    # ------------------------------------------------------------------ #

    def query_doc_rows_by_file_title(self, file_title: str) -> list[dict]:
        """按 file_title 查回全部 docs 行 (含 id / task_id)。

        同名覆盖时用于找到旧文档: 完整删除旧 chunks / docs / MinIO 制品。
        consistency_level=Strong: 保证能看到刚插入的行, 规避 Bounded 一致性的
        延迟可见窗口 (否则快速重导入时可能查不到旧行)。
        """
        res = self.query(
            collection_name=ENV_CONFIG.milvus.collection_docs,
            filter=f'{MilvusDocsField.FILE_TITLE} == "{_escape_milvus_str(file_title)}"',
            output_fields=[MilvusDocsField.ID, MilvusDocsField.TASK_ID],
            limit=16384,
            consistency_level="Strong",
        )
        return list(res) if res else []

    def query_doc_id(self, task_id: str, file_title: str) -> int | None:
        """docs 写入后按 task_id + file_title 查回主键 id (兜底)。

        task_id + file_title 组合唯一, 查询无歧义; 按 id 降序取第一条,
        兜底规避 Milvus delete 延迟可见时新旧行短暂并存。
        consistency_level=Strong: 保证刚插入的行立即可见。
        """
        res = self.query(
            collection_name=ENV_CONFIG.milvus.collection_docs,
            filter=(
                f'{MilvusDocsField.TASK_ID} == "{_escape_milvus_str(task_id)}" and '
                f'{MilvusDocsField.FILE_TITLE} == "{_escape_milvus_str(file_title)}"'
            ),
            output_fields=[MilvusDocsField.ID],
            limit=16384,
            consistency_level="Strong",
        )
        if not res:
            return None
        return max(row[MilvusDocsField.ID] for row in res)

    def delete_docs_by_file_title(self, file_title: str) -> None:
        """按 file_title 删除全部 docs 行 (同名覆盖的旧行清理)。"""
        self.delete(
            collection_name=ENV_CONFIG.milvus.collection_docs,
            filter=f'{MilvusDocsField.FILE_TITLE} == "{_escape_milvus_str(file_title)}"',
        )

    def delete_chunks_by_doc_ids(self, doc_ids: list[int]) -> None:
        """按 doc_id 精确删除 chunks (同名覆盖时先删旧切片)。"""
        if not doc_ids:
            return
        self.delete(
            collection_name=ENV_CONFIG.milvus.collection_chunks,
            filter=f"{MilvusChunksField.DOC_ID} in {doc_ids}",
        )

    def delete_chunks_by_file_title(self, file_title: str) -> None:
        """按 file_title 删除 chunks (历史遗留行的兜底清理)。"""
        self.delete(
            collection_name=ENV_CONFIG.milvus.collection_chunks,
            filter=(
                f'{MilvusChunksField.FILE_TITLE} == "{_escape_milvus_str(file_title)}"'
            ),
        )

    # ------------------------------------------------------------------ #
    # 集合初始化
    # ------------------------------------------------------------------ #

    def prepare_docs_collection(self):
        """准备 docs collection, 有则跳过, 无则创建"""
        collection_name = ENV_CONFIG.milvus.collection_docs
        has_collection = self.has_collection(collection_name)
        if has_collection:
            logger.info(f"Milvus collection '{collection_name}' 已存在")
            return

        # 创建 schema
        # https://milvus.io/docs/schema.md#Create-Schema
        schema = self.create_schema(auto_id=True)
        schema.add_field(
            field_name=MilvusDocsField.ID,
            datatype=DataType.INT64,
            is_primary=True,
        ).add_field(
            field_name=MilvusDocsField.TASK_ID,
            datatype=DataType.VARCHAR,
            max_length=256,
        ).add_field(
            field_name=MilvusDocsField.FILE_TITLE,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusDocsField.ORIGIN_FILE_URL,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusDocsField.FINAL_MARKDOWN_URL,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusDocsField.CHUNKS_URL,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusDocsField.DOCS_KEYWORDS,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusDocsField.DOCS_ABSTRACT,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusDocsField.ABSTRACT_DENSE_VECTOR,
            datatype=DataType.FLOAT_VECTOR,
            dim=ENV_CONFIG.embedding.dense_dimension,
        ).add_field(
            field_name=MilvusDocsField.KEYWORDS_SPARSE_VECTOR,
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )

        # 创建索引参数 0.主键索引(auto) 1. 摘要稠密向量索引 2. 关键词稀疏向量索引
        index_params = self.prepare_index_params()

        # =========================
        # 稠密向量索引：abstract_dense_vector
        # =========================
        index_params.add_index(
            field_name=MilvusDocsField.ABSTRACT_DENSE_VECTOR,
            index_name=MilvusDocsIndex.ABSTRACT_DENSE_VECTOR_INDEX,
            metric_type="COSINE",  # 距离度量方式，COSINE 表示余弦相似度
            index_type="HNSW",  # 索引算法类型，HNSW 分层导航小世界
            params={  # HNSW 算法专属参数
                "M": 64,  # 每个节点的最大出边数，越大召回越高、内存越大、构建越慢
                "efConstruction": 100,  # 构建索引时的候选队列大小，越大索引质量越高、构建越慢
            },
        )

        # 稀疏字段
        index_params.add_index(
            field_name=MilvusDocsField.KEYWORDS_SPARSE_VECTOR,
            index_name=MilvusDocsIndex.KEYWORDS_SPARSE_VECTOR_INDEX,
            metric_type="IP",  # 距离度量方式，IP 表示内积
            index_type="SPARSE_INVERTED_INDEX",  # 索引算法类型，稀疏向量使用倒排索引
            params={
                "inverted_index_algo": "DAAT_MAXSCORE"
            },  # 倒排索引算法专用参数，动态剪枝，加速稀疏向量的 top-k 检索
        )

        # 创建 collection
        self.create_collection(
            collection_name=collection_name, schema=schema, index_params=index_params
        )

    def prepare_chunks_collection(self):
        """准备 chunks collection, 有则跳过, 无则创建"""
        collection_name = ENV_CONFIG.milvus.collection_chunks

        # 如果 collection 已经存在，则直接返回
        has_collection = self.has_collection(collection_name)
        if has_collection:
            logger.info(f"Milvus collection '{collection_name}' 已存在")
            return

        # 创建 schema
        schema = self.create_schema(auto_id=True)
        schema.add_field(
            field_name=MilvusChunksField.ID,
            datatype=DataType.INT64,
            is_primary=True,
        ).add_field(
            field_name=MilvusChunksField.DOC_ID,
            datatype=DataType.INT64,
        ).add_field(
            field_name=MilvusChunksField.FILE_TITLE,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusChunksField.CHUNK_INDEX,
            datatype=DataType.INT64,
        ).add_field(
            field_name=MilvusChunksField.CHUNK_CONTENT,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusChunksField.CONTENT_DENSE_VECTOR,
            datatype=DataType.FLOAT_VECTOR,
            dim=ENV_CONFIG.embedding.dense_dimension,
        ).add_field(
            field_name=MilvusChunksField.CONTENT_SPARSE_VECTOR,
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )

        # 创建索引参数
        index_params = self.prepare_index_params()

        # 稠密向量索引：content_dense_vector
        index_params.add_index(
            field_name=MilvusChunksField.CONTENT_DENSE_VECTOR,
            index_name=MilvusChunksIndex.CONTENT_DENSE_VECTOR_INDEX,
            metric_type="COSINE",
            index_type="HNSW",
            params={
                "M": 64,
                "efConstruction": 100,
            },
        )

        # 稀疏字段
        index_params.add_index(
            field_name=MilvusChunksField.CONTENT_SPARSE_VECTOR,
            index_name=MilvusChunksIndex.CONTENT_SPARSE_VECTOR_INDEX,
            metric_type="IP",
            index_type="SPARSE_INVERTED_INDEX",
            params={"inverted_index_algo": "DAAT_MAXSCORE"},
        )

        # 创建 collection
        self.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )


if __name__ == "__main__":
    milvus_client = MiniRagMilvusClient()
    milvus_client.prepare_docs_collection()
    milvus_client.prepare_chunks_collection()
