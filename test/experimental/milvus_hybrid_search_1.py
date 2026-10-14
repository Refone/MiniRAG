from pymilvus import (
    AnnSearchRequest,
    RRFRanker,
    connections,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
)
import random

# 连接 Milvus
connections.connect(host="127.0.0.1", port="19530")

# 定义 Schema，包含两个向量字段
fields = [
    FieldSchema(name="film_id", dtype=DataType.INT64, is_primary=True),
    FieldSchema(
        name="filmVector", dtype=DataType.FLOAT_VECTOR, dim=5
    ),  # 例如：电影内容向量
    FieldSchema(
        name="posterVector", dtype=DataType.FLOAT_VECTOR, dim=5
    ),  # 例如：海报图像向量
]
schema = CollectionSchema(fields=fields, enable_dynamic_field=False)

# 创建 Collection
# 先删除 test_collection
Collection(name="test_collection").drop()
collection = Collection(name="test_collection", schema=schema)

# 为每个向量字段创建索引
index_params = {"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}}
collection.create_index("filmVector", index_params)
collection.create_index("posterVector", index_params)

# ========== 插入数据 ==========
entities = []
for i in range(1000):
    entity = {
        "film_id": i,
        "filmVector": [random.random() for _ in range(5)],
        "posterVector": [random.random() for _ in range(5)],
    }
    entities.append(entity)
collection.insert(entities)

collection.load()
# ========== 创建 AnnSearchRequest 实例 ==========

# 为 filmVector 创建搜索请求
search_param_1 = {
    "data": [[0.1, 0.2, 0.3, 0.4, 0.5]],  # 查询向量
    "anns_field": "filmVector",
    "param": {"metric_type": "L2", "params": {"nprobe": 10}},
    "limit": 10,
}
request_1 = AnnSearchRequest(**search_param_1)

# 为 posterVector 创建搜索请求
search_param_2 = {
    "data": [[0.2, 0.3, 0.4, 0.5, 0.6]],
    "anns_field": "posterVector",
    "param": {"metric_type": "L2", "params": {"nprobe": 10}},
    "limit": 10,
}
request_2 = AnnSearchRequest(**search_param_2)


# ============== 执行混合搜索 =============
# 使用 RRFRanker（互易等级融合）进行重排序
rerank = RRFRanker(k=60)  # k 为平滑参数，通常设为 60

# 或者使用 WeightedRanker（加权评分）
# rerank = WeightedRanker(0.7, 0.3)  # 分别为两路结果分配权重

# 执行混合搜索
results = collection.hybrid_search(
    reqs=[request_1, request_2], rerank=rerank, limit=5, output_fields=["film_id"]
)

from rich import print as rprint

rprint(results)
