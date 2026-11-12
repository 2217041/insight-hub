"""W11：chunk.embedding 维度 1024 → 512

换成 bge-small-zh-v1.5（512 维）。原来的向量列全是 NULL，
所以直接 ALTER TYPE 即可；如果有数据，需要先清空或用 USING 转换。
"""

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b8ddbd5221b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 换维度前必须确保没有旧维度的向量；当前全为 NULL
    op.execute("UPDATE chunk SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute("ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(512)")


def downgrade() -> None:
    op.execute("UPDATE chunk SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute("ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(1024)")