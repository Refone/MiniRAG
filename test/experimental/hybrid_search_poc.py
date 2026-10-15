from pymilvus import DataType, DataType
from common.client import MILVUS_CLIENT
from common.model import EMBEDDING


class _FieldName:
    ID = "id"
    TEXT = "text"
    DENSE_VECTOR = "dense_vector"
    SPARSE_VECTOR = "sparse_vector"


class _IndexName:
    DENSE_VECTOR_INDEX = "dense_vector_index"
    SPARSE_VECTOR_INDEX = "sparse_vector_index"


collection_name = "test_collection"


def prepare_test_collection():
    # 如果 collection 已经存在，则直接返回
    has_collection = MILVUS_CLIENT.has_collection(collection_name)
    if has_collection:
        MILVUS_CLIENT.drop_collection(collection_name)

    # 如果 collection 不存在，则创建
    # 创建 schema
    # https://milvus.io/docs/schema.md#Create-Schema
    schema = MILVUS_CLIENT.create_schema(auto_id=True)
    schema.add_field(
        field_name=_FieldName.ID,
        datatype=DataType.INT64,
        is_primary=True,
    ).add_field(
        field_name=_FieldName.TEXT,
        datatype=DataType.VARCHAR,
        max_length=0xFFFF,
    ).add_field(
        field_name=_FieldName.DENSE_VECTOR,
        datatype=DataType.FLOAT_VECTOR,
        dim=1024,
    ).add_field(
        field_name=_FieldName.SPARSE_VECTOR,
        datatype=DataType.SPARSE_FLOAT_VECTOR,
    )

    # 创建索引参数 0.主键索引(auto) 1. 稠密向量索引 2. 稀疏向量索引
    index_params = MILVUS_CLIENT.prepare_index_params()

    # =========================
    # 稠密向量索引：dense_vector
    # =========================
    index_params.add_index(
        field_name=_FieldName.DENSE_VECTOR,  # 与 schema 中的字段一致, 需要建索引的字段
        index_name=_IndexName.DENSE_VECTOR_INDEX,  # 自定义索引名称
        metric_type="COSINE",  # 距离度量方式，COSINE 表示余弦相似度
        index_type="HNSW",  # 索引算法类型，HNSW 分层导航小世界
        params={  # HNSW 算法专属参数
            "M": 64,  # 每个节点的最大出边数，越大召回越高、内存越大、构建越慢
            "efConstruction": 100,  # 构建索引时的候选队列大小，越大索引质量越高、构建越慢
        },
    )

    # 稀疏字段
    index_params.add_index(
        field_name=_FieldName.SPARSE_VECTOR,  # 与 schema 中的字段一致, 需要建索引的字段
        index_name=_IndexName.SPARSE_VECTOR_INDEX,  # 自定义索引名称
        metric_type="IP",  # 距离度量方式，IP 表示内积
        index_type="SPARSE_INVERTED_INDEX",  # 索引算法类型，稀疏向量使用倒排索引
        params={
            "inverted_index_algo": "DAAT_MAXSCORE"
        },  # 倒排索引算法专用参数，动态剪枝，加速稀疏向量的 top-k 检索
    )

    # 创建 collection
    MILVUS_CLIENT.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )


def _insert_one_data(text: str):
    vecs = EMBEDDING.embed_document_hybrid([text])
    dense_vector = vecs[0]["dense"]
    sparse_vector = vecs[0]["sparse"]

    MILVUS_CLIENT.insert(
        collection_name=collection_name,
        data=[
            {
                "text": text,
                "dense_vector": dense_vector,
                "sparse_vector": sparse_vector,
            }
        ],
    )


def test_query(text: str):
    vecs = EMBEDDING.embed_document_hybrid([text])
    dense_vector = vecs[0]["dense"]
    sparse_vector = vecs[0]["sparse"]

    results = MILVUS_CLIENT.minirag_hybrid_search(
        collection_name=collection_name,
        dense_vectors=[dense_vector],
        sparse_vectors=[sparse_vector],
    )

    return results


def insert_test_data(data: list[str]):
    """
    插入测试数据
    :param collection_name: collection 名称
    :param data: 数据列表，每个元素是一个字典，包含字段名和对应的值
    """
    for text in data:
        _insert_one_data(text=text)


def parse_result(results):
    parsed_results = []
    for result in results:
        parsed_results.append(
            {
                "entity_text": result["entity"]["text"],
                "score": result["distance"],
            }
        )
    return parsed_results


if __name__ == "__main__":
    from rich import print as rprint

    query_data = "HAK180"
    db_data = [
        "HAK180烫金机说明书",
        "HAK 180 烫金机",
        "万用表 RS-12",
        "万用表RS-12使用说明书",
        "DX5000 3D打印机",
        "IPhone 17 Pro Max 1T",
        "MacBook Pro 16 2023",
        "戴森 Dyson 吸尘器",
        "Dell 笔记本电脑",
    ]

    prepare_test_collection()

    insert_test_data(db_data)

    results = test_query(query_data)

    print(f"搜索:[{query_data}]")
    rprint(parse_result(results[0]))
