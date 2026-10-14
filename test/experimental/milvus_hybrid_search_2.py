import random
from pymilvus import (
    MilvusClient,
    DataType,
    AnnSearchRequest,
    RRFRanker,
)

COLLECTION = "test_collection"
DIM = 5

# 1. 连接（MilvusClient 一步搞定，无需 connections.connect）
client = MilvusClient(uri="http://127.0.0.1:19530")

# 2. 清理旧集合
if client.has_collection(COLLECTION):
    client.drop_collection(COLLECTION)

# 3. 定义 Schema（用 MilvusClient 的 create_schema）
schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
schema.add_field("film_id", DataType.INT64, is_primary=True)
schema.add_field("filmVector", DataType.FLOAT_VECTOR, dim=DIM)
schema.add_field("posterVector", DataType.FLOAT_VECTOR, dim=DIM)

# 4. 索引参数
index_params = client.prepare_index_params()
index_params.add_index(
    field_name="filmVector",
    index_type="IVF_FLAT",
    metric_type="L2",
    params={"nlist": 128},
)
index_params.add_index(
    field_name="posterVector",
    index_type="IVF_FLAT",
    metric_type="L2",
    params={"nlist": 128},
)

# 5. 创建集合（带 schema + index，创建后自动 load）
client.create_collection(
    collection_name=COLLECTION,
    schema=schema,
    index_params=index_params,
)

# 6. 插入数据
entities = [
    {
        "film_id": i,
        "filmVector": [random.random() for _ in range(DIM)],
        "posterVector": [random.random() for _ in range(DIM)],
    }
    for i in range(1000)
]
client.insert(collection_name=COLLECTION, data=entities)

# 7. 确保数据可见 + 加载（create_collection 已带 index 时会自动 load，
#    但显式调用更稳妥，尤其插入新数据后）
client.flush(COLLECTION)
client.load_collection(COLLECTION)  # ← 对应 ORM 的 collection.load()

# 8. 构造两路 AnnSearchRequest
req_1 = AnnSearchRequest(
    data=[[0.1, 0.2, 0.3, 0.4, 0.5]],
    anns_field="filmVector",
    param={"metric_type": "L2", "params": {"nprobe": 10}},
    limit=10,
)
req_2 = AnnSearchRequest(
    data=[[0.2, 0.3, 0.4, 0.5, 0.6]],
    anns_field="posterVector",
    param={"metric_type": "L2", "params": {"nprobe": 10}},
    limit=10,
)

# 9. 混合检索
results = client.hybrid_search(
    collection_name=COLLECTION,
    reqs=[req_1, req_2],
    ranker=RRFRanker(k=60),  # 注意：MilvusClient 里参数名是 ranker
    limit=5,
    output_fields=["film_id"],
)

for hits in results:
    for hit in hits:
        print(hit)
