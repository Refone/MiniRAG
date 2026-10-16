from typing import TypedDict


# kb_item_name 表相关类型定义
class MilvusItemNameField:
    ID = "id"
    FILE_TITLE = "file_title"
    ITEM_NAME = "item_name"
    DENSE_VECTOR = "dense_vector"
    SPARSE_VECTOR = "sparse_vector"


class MilvusItemNameIndex:
    DENSE_VECTOR_INDEX = "dense_vector_index"
    SPARSE_VECTOR_INDEX = "sparse_vector_index"


class MilvusItemNameItem(TypedDict):
    id: str
    file_title: str
    item_name: str
    dense_vector: list[float]
    sparse_vector: dict[int, float]


# kb_chunks 表相关类型定义
class MilvusChunksField:
    ID = "id"
    FILE_TITLE = "file_title"
    ITEM_NAME = "item_name"
    CHUNK_CONTENT = "chunk_content"
    DENSE_VECTOR = "dense_vector"
    SPARSE_VECTOR = "sparse_vector"


class MilvusChunksIndex:
    DENSE_VECTOR_INDEX = "dense_vector_index"
    SPARSE_VECTOR_INDEX = "sparse_vector_index"


class MilvusChunksItem(TypedDict):
    id: str
    file_title: str
    item_name: str
    chunk_content: str
    dense_vector: list[float]
    sparse_vector: dict[int, float]
