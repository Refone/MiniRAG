from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from utils.path_utils import PROJECT_ROOT

"""
    该文件从 .env 文件中读取配置信息
    读取规则:
    TODO
"""
BASE_DIR = PROJECT_ROOT
ENV_FILE = BASE_DIR / ".env"

BASE_CONFIG = {"env_file": ENV_FILE, "env_file_encoding": "utf-8", "extra": "ignore"}


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class QwenSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="QWEN_")

    base_url: str = "https://maas.qianwenaiapi.com/compatible-mode/v1"
    api_key: str = ""


class LogSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="LOG_")

    console_enable: bool = False
    console_level: LogLevel = LogLevel.INFO
    file_enable: bool = False
    file_level: LogLevel = LogLevel.DEBUG
    file_retention: str = "7 days"
    file_dir: str = str(PROJECT_ROOT / "logs")


class MineruSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MINERU_")

    base_url: str = "https://mineru.net/api/v4"
    api_key: str = ""
    est_per_page: float = 0.5
    timeout_per_page: float = 10
    poll_interval: float = 3
    unzip_dir: str = str(PROJECT_ROOT / "output/import")


class VLMSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="VLM_")

    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model_name: str = "Qwen/Qwen3-VL-32B-Instruct"
    rpm: int = 1000
    # 图片摘要并发请求数 (node_md_img 用线程池并发调 VLM)
    concurrency: int = 8


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MINIO_")

    endpoint: str = "127.0.0.1:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket_name: str = "minirag"
    image_dir: str = "markdown-images"
    # 文档三份制品 (原始文件 / 最终 markdown / chunks.json) 的目录,
    # 对象路径为 <dir>/<task_id>/<file_title>/<文件名>
    origin_dir: str = "origin-files"
    markdown_dir: str = "final-markdowns"
    chunks_dir: str = "chunks-json"
    secure: bool = False


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="EMBEDDING_")

    model: str = "text-embedding-v4"
    rpm: int = 1000
    dense_dimension: int = 1024
    concurrency: int = 8
    batch_size: int = 10


class RerankSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="RERANK_")

    model: str = "qwen3.7-text-rerank"
    base_url: str = "https://maas.qianwenaiapi.com/api/v1"
    rpm: int = 3000
    max_length: int = 30_000


class MilvusSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MILVUS_")

    endpoint: str = "127.0.0.1:19530"
    collection_docs: str = "minirag_docs"
    collection_chunks: str = "minirag_chunks"


class LargeLanguageModelSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="LLM_")

    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model_name: str = "deepseek-ai/DeepSeek-V4-Flash"
    rpm: int = 500
    timeout: float = 120.0
    max_retries: int = 2


class MongoDBSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="MONGODB_")

    uri: str = "mongodb://localhost:27017"
    db_name: str = "minirag"


class DashscopeSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_CONFIG, env_prefix="DASHSCOPE_")

    api_key: str = ""
    web_search_mcp_url: str = "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"
    web_search_mcp_tool_name: str = "bailian_web_search"


class EnvConfig(BaseSettings):
    log: LogSettings = Field(default_factory=LogSettings)
    mineru: MineruSettings = Field(default_factory=MineruSettings)
    vlm: VLMSettings = Field(default_factory=VLMSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    qwen: QwenSettings = Field(default_factory=QwenSettings)
    mongodb: MongoDBSettings = Field(default_factory=MongoDBSettings)
    llm: LargeLanguageModelSettings = Field(default_factory=LargeLanguageModelSettings)
    dashscope: DashscopeSettings = Field(default_factory=DashscopeSettings)


ENV_CONFIG = EnvConfig()

if __name__ == "__main__":
    from rich import print as rprint

    rprint(ENV_CONFIG)
