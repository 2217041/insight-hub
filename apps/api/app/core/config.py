"""应用配置：从环境变量/.env 读取，带默认值。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Insight Hub API"
    app_version: str = "0.5.0"

    database_url: str = "postgresql+psycopg://insight:insight@127.0.0.1:5432/insight"
    redis_url: str = "redis://127.0.0.1:6379/0"

    jwt_secret: str = "dev-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # ---- W5：文件上传与异步管道 ----
    storage_dir: str = "data/uploads"
    upload_max_bytes: int = 20 * 1024 * 1024  # 20 MB
    allowed_extensions: list[str] = [".txt", ".md", ".markdown", ".pdf", ".docx"]
    # 文档列表缓存（秒）；写操作会主动失效
    doc_list_cache_ttl: int = 30
    # 单租户每分钟最多上传次数
    upload_rate_per_minute: int = 10

    # ---- W9：大模型接入 ----
    # provider: mock（占位）| openai（任何 OpenAI 兼容 API）| ollama（本地）
    llm_provider: str = "mock"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024
    # 带多少轮历史（每轮 2 条），太多会导致上下文爆炸
    llm_max_history_messages: int = 12
    # 计费（元 / 百万 token），用于成本统计；不同模型自己改
    llm_price_in_per_1m: float = 1.0
    llm_price_out_per_1m: float = 2.0

    # ---- W11：向量化与检索 ----
    # local = fastembed(ONNX) 本地模型；openai = 任意兼容 /embeddings 的 API
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_cache_dir: str = "data/models"
    embedding_batch: int = 32
    # 检索：召回候选数与最终给模型的块数
    retrieval_candidates: int = 20
    retrieval_top_k: int = 5


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()