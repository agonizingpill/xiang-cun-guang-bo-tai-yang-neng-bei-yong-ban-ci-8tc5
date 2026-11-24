from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String, Table

from core.db import metadata


airslots = Table('airslots', metadata,
    Column('code', String(64), primary_key=True),
    Column('title', String(160), nullable=False),
    Column('hour', Integer, nullable=False),
    # 节目档所属的共用电池；同一块电池下的各档并发发卡共用一块额度。
    Column('battery', String(64), ForeignKey('batteries.code'), nullable=False),
    Column('license', String(160), nullable=False),
    Column('offline', Boolean, nullable=False),
    CheckConstraint('hour between 0 and 23'),
)
