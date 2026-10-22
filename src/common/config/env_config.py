from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from utils.path_utils import PROJECT_ROOT

"""
    该文件从 PROJECT_ROOT/.env 文件中读取配置信息
"""
BASE_CONFIG = {
    "env_file": PROJECT_ROOT / ".env",
    "env_file_encoding": "utf-8",
    "extra": "ignore",
}


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class OutputDirSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="OUTPUT_DIR_")

    import_tmp_dir: str = str(PROJECT_ROOT / "output/import")
    upload_tmp_dir: str = str(PROJECT_ROOT / "output/uploads")
    log_dir: str = str(PROJECT_ROOT / "output/logs")


class LogSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="LOG_")

    console_enable: bool = False
    console_level: LogLevel = LogLevel.INFO
    file_enable: bool = False
    file_level: LogLevel = LogLevel.DEBUG
    file_retention: str = "7 days"


class MineruSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MINERU_")

    base_url: str = "https://mineru.net/api/v4"
    api_key: str = ""


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MINIO_")

    endpoint: str = "127.0.0.1:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket_name: str = "minirag"
    image_dir: str = "markdown-images"
    origin_dir: str = "origin-files"
    markdown_dir: str = "final-markdowns"
    chunks_dir: str = "chunks-json"
    secure: bool = False


class MilvusSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MILVUS_")

    endpoint: str = "127.0.0.1:19530"
    collection_docs: str = "minirag_docs"
    collection_chunks: str = "minirag_chunks"


class MongoDBSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MONGODB_")

    uri: str = "mongodb://localhost:27017"
    db_name: str = "minirag"


class DashscopeSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="DASHSCOPE_")

    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # LLM
    llm_model: str = "deepseek-v4.1-flash"
    llm_rpm: int = 500
    llm_tpm: int = 1000000

    # VLM
    vlm_model: str = "qwen3-vl-plus"
    vlm_rpm: int = 3000
    vlm_tpm: int = 5000000

    # Embedding
    embedding_model: str = "text-embedding-v4"
    embedding_rpm: int = 1000
    embedding_tpm: int = 1000000
    embedding_dense_dimension: int = 1024
    embedding_batch_size: int = 10

    # Reranker
    rerank_model: str = "qwen3.7-text-rerank"
    rerank_rpm: int = 3000
    rerank_tpm: int = 9000000
    rerank_max_text_length: int = 30000

    # Web Search MCP
    web_search_mcp_url: str = "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"
    web_search_mcp_tool_name: str = "bailian_web_search"


class EnvConfig(BaseSettings):
    output_dir: OutputDirSettings = Field(default_factory=OutputDirSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    mineru: MineruSettings = Field(default_factory=MineruSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    mongodb: MongoDBSettings = Field(default_factory=MongoDBSettings)
    dashscope: DashscopeSettings = Field(default_factory=DashscopeSettings)


ENV_CONFIG = EnvConfig()

if __name__ == "__main__":
    from rich import print as rprint

    rprint(ENV_CONFIG)
