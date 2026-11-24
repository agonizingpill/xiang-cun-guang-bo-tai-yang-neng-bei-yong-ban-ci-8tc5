from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, String, Table

from core.db import metadata


# 状态机：值守签发（占额）→ 已闭台 WR-xx（仍占额）；
# 值守签发 → 已撤卡（释放额度，撤卡重试幂等不重复退）。
switchcards = Table('switchcards', metadata,
    Column('code', String(64), primary_key=True),
    Column('reserve', String(160), ForeignKey('reserves.code'), nullable=False, unique=True),
    Column('source', String(160), nullable=False),
    Column('approved_wh', Float, nullable=False),
    Column('state', String(160), nullable=False),
    CheckConstraint('approved_wh >= 0'),
    CheckConstraint("state in ('值守签发', '已撤卡') or state like '已闭台 %'"),
)
