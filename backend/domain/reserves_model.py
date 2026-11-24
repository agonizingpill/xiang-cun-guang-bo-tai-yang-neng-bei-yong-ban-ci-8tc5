from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, String, Table

from core.db import metadata


reserves = Table('reserves', metadata,
    Column('code', String(64), primary_key=True),
    Column('airslot', String(160), ForeignKey('airslots.code'), nullable=False),
    Column('meter', String(160), nullable=False),
    # 整班点预测：整班窗口内逐小时截零预测之和（不含余量）。
    Column('prediction_wh', Float, nullable=False),
    # 建议发卡额 = 点预测 + 整班 MAE（留出段内等长时窗）。
    Column('plan_wh', Float, nullable=False),
    Column('fallback', String(160), nullable=False),
    # 整班平均绝对误差（等长时窗），同时作为该电池公用余量的最近一次测算。
    Column('mae', Float, nullable=False),
    Column('token', String(64), nullable=False, unique=True),
    CheckConstraint('prediction_wh >= 0'),
    CheckConstraint('plan_wh >= 0'),
    CheckConstraint('mae >= 0'),
)
