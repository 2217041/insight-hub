"""集中导出所有模型。

**必须在这里 import 每一张表**，否则 Alembic 的 autogenerate 看不到它，
生成的迁移会漏表——这是最典型的"迁移少了一张表"的原因。
"""

from app.models.agent_run import AgentRun, EvalRun
from app.models.chunk import EMBEDDING_DIM, Chunk
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "AgentRun",
    "Chunk",
    "Conversation",
    "Document",
    "EMBEDDING_DIM",
    "EvalRun",
    "Message",
    "Tenant",
    "User",
]