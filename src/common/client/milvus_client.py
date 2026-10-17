from common.schemas.external_schemas.milvus_schemas import *
from common.config.app_config import APP_CONFIG
from common.model import EMBEDDING
from utils.logging_utils import logger
from common.config.env_config import ENV_CONFIG
from pymilvus import AnnSearchRequest, DataType, MilvusClient, WeightedRanker


class MiniRagMilvusClient(MilvusClient):
    def __init__(self):
        super().__init__(uri=ENV_CONFIG.milvus.endpoint)

    def hybrid_search_item_name(
        self,
        texts: list[str],
        limit: int = APP_CONFIG.item_name_recall_limit,
    ) -> list[list[dict]] | None:
        collection_name = ENV_CONFIG.milvus.collection_item_name
        output_fields = [MilvusItemNameField.ITEM_NAME]

        texts_vectors = EMBEDDING.embed_query_hybrid(texts)
        """
        texts_vectors:
        [
            {'dense':[...], 'sparse':[...]},
            {'dense':[...], 'sparse':[...]},
            ...
        ]
        """
        dense_vectors = [vec["dense"] for vec in texts_vectors]
        sparse_vectors = [vec["sparse"] for vec in texts_vectors]

        return self.minirag_hybrid_search(
            collection_name=collection_name,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            output_fields=output_fields,
            weight=APP_CONFIG.item_name_hybrid_weight,
            limit=limit,
        )

    def hybrid_search_chunks(
        self,
        query_text: list[str],
        item_names: list[str] = None,
        limit: int = APP_CONFIG.chunks_recall_limit,
    ) -> list[list[dict]] | None:
        collection_name = ENV_CONFIG.milvus.collection_chunks
        output_fields = [
            MilvusChunksField.ITEM_NAME,
            MilvusChunksField.FILE_TITLE,
            MilvusChunksField.CHUNK_CONTENT,
        ]

        vectors = EMBEDDING.embed_query_hybrid(query_text)
        """
        vectors:
        [
            {'dense':[...], 'sparse':[...]},
            {'dense':[...], 'sparse':[...]},
            ...
        ]
        """
        dense_vector = [vec["dense"] for vec in vectors]
        sparse_vector = [vec["sparse"] for vec in vectors]

        return self.minirag_hybrid_search(
            collection_name=collection_name,
            dense_vectors=dense_vector,
            sparse_vectors=sparse_vector,
            limit=limit,
            weight=APP_CONFIG.chunks_hybrid_weight,
            filter=f"item_name in {item_names}" if item_names else None,
            output_fields=output_fields,
        )

    # Milvus 混合搜索 (稠密向量 + 稀疏向量)
    # https://milvus.io/docs/multi-vector-search.md
    # https://milvus.io/api-reference/pymilvus/v3.0.x/MilvusClient/Vector/hybrid_search.md
    # 反省: anns_field 封在这里面其实不算好的设计, 未来可能出现多向量字段的场景
    def minirag_hybrid_search(
        self,
        collection_name: str,
        dense_vectors: list[list[float]],
        sparse_vectors: list[dict[int, float]],
        limit: int,
        weight: tuple[float, float],
        filter: str | None = None,
        output_fields: list[str] = ["*"],
    ) -> list[list[dict]] | None:
        """稠密 + 稀疏混合搜索, 支持批量查询 (nq > 1)。

        返回 list[list[dict]]: 外层长度 = 查询向量个数 (nq),
        内层是该查询融合后按得分排序的 top-k 命中; 搜索失败返回 None。
        返回格式：
        [
            [  # 第一个查询向量的命中
                {
                    "id": 469734951640943804,
                    "distance": 0.8866561651229858,
                    "entity": {
                        "item_name": ...
                    }
                },
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
            anns_field=MilvusItemNameField.DENSE_VECTOR,
            param={
                "metric_type": "COSINE",
            },  # 更多 ANN 参数设置也是在这个字典里
            limit=limit,  # 每个请求返回的最大结果数
            filter=filter,  # 可选的过滤条件
        )
        sparse_req = AnnSearchRequest(
            data=sparse_vectors,
            anns_field=MilvusItemNameField.SPARSE_VECTOR,
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

    def prepare_item_name_collection(self):
        """准备 item_name collection, 有则跳过, 无则创建"""
        collection_name = ENV_CONFIG.milvus.collection_item_name
        has_collection = self.has_collection(collection_name)
        if has_collection:
            logger.info(f"Milvus collection '{collection_name}' 已存在")
            return

        # 如果 collection 不存在，则创建
        # 创建 schema
        # https://milvus.io/docs/schema.md#Create-Schema
        schema = self.create_schema(auto_id=True)
        schema.add_field(
            field_name=MilvusItemNameField.ID,
            datatype=DataType.INT64,
            is_primary=True,
        ).add_field(
            field_name=MilvusItemNameField.FILE_TITLE,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusItemNameField.ITEM_NAME,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusItemNameField.DENSE_VECTOR,
            datatype=DataType.FLOAT_VECTOR,
            dim=1024,
        ).add_field(
            field_name=MilvusItemNameField.SPARSE_VECTOR,
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )

        # 创建索引参数 0.主键索引(auto) 1. 稠密向量索引 2. 稀疏向量索引
        index_params = self.prepare_index_params()

        # =========================
        # 稠密向量索引：dense_vector
        # =========================
        index_params.add_index(
            field_name=MilvusItemNameField.DENSE_VECTOR,  # 与 schema 中的字段一致, 需要建索引的字段
            index_name=MilvusItemNameIndex.DENSE_VECTOR_INDEX,  # 自定义索引名称
            metric_type="COSINE",  # 距离度量方式，COSINE 表示余弦相似度
            index_type="HNSW",  # 索引算法类型，HNSW 分层导航小世界
            params={  # HNSW 算法专属参数
                "M": 64,  # 每个节点的最大出边数，越大召回越高、内存越大、构建越慢
                "efConstruction": 100,  # 构建索引时的候选队列大小，越大索引质量越高、构建越慢
            },
        )

        # 稀疏字段
        index_params.add_index(
            field_name=MilvusItemNameField.SPARSE_VECTOR,  # 与 schema 中的字段一致, 需要建索引的字段
            index_name=MilvusItemNameIndex.SPARSE_VECTOR_INDEX,  # 自定义索引名称
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

        # 如果 collection 不存在，则创建
        # 创建 schema
        schema = self.create_schema(auto_id=True)
        schema.add_field(
            field_name=MilvusChunksField.ID,
            datatype=DataType.INT64,
            is_primary=True,
        ).add_field(
            field_name=MilvusChunksField.FILE_TITLE,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusChunksField.ITEM_NAME,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusChunksField.CHUNK_CONTENT,
            datatype=DataType.VARCHAR,
            max_length=0xFFFF,
        ).add_field(
            field_name=MilvusChunksField.DENSE_VECTOR,
            datatype=DataType.FLOAT_VECTOR,
            dim=1024,
        ).add_field(
            field_name=MilvusChunksField.SPARSE_VECTOR,
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )

        # 创建索引参数
        index_params = self.prepare_index_params()

        # 稠密向量索引：dense_vector
        index_params.add_index(
            field_name=MilvusChunksField.DENSE_VECTOR,
            index_name=MilvusChunksIndex.DENSE_VECTOR_INDEX,
            metric_type="COSINE",
            index_type="HNSW",
            params={
                "M": 64,
                "efConstruction": 100,
            },
        )

        # 稀疏字段
        index_params.add_index(
            field_name=MilvusChunksField.SPARSE_VECTOR,
            index_name=MilvusChunksIndex.SPARSE_VECTOR_INDEX,
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
    milvus_client.prepare_item_name_collection()
    milvus_client.prepare_chunks_collection()
