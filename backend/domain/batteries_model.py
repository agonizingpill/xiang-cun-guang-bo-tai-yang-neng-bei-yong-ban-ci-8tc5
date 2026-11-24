from sqlalchemy import CheckConstraint, Column, Float, Integer, String, Table

from core.db import metadata


# 几档连播节目共用一块电池：电池以同一电表的审签读数计量，
# 整班（shift_hours）长度决定留出段内等长时窗与各档预测窗口。
batteries = Table('batteries', metadata,
    Column('code', String(64), primary_key=True),
    Column('meter', String(160), nullable=False, unique=True),
    Column('shift_hours', Integer, nullable=False),
    Column('capacity_wh', Float, nullable=False),
    # 公用余量：留出段内等长时窗的整班平均绝对误差，由最近一次评估写入。
    Column('margin_wh', Float, nullable=False, server_default='0'),
    CheckConstraint('shift_hours between 1 and 6'),
    CheckConstraint('capacity_wh > 0'),
    CheckConstraint('margin_wh >= 0'),
)
