"""测试引导：隔离环境变量 + SQLite + 假 Redis，须以 python -I 运行。"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:////tmp/hamlet_test.sqlite3')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6399/0')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ['SEED_DEMO'] = 'false'

import fakeredis  # noqa: E402

import core.queueing as queueing  # noqa: E402
import core.db as db  # noqa: E402

queueing.broker = fakeredis.FakeRedis()

from sqlalchemy import text  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

# 显式导入全部模型，确保 metadata 注册表在任何 engine 上都能建齐。
from domain import airslots_model, batteries_model, battery_logs_model  # noqa: E402
from domain import reserves_model, switchcards_model  # noqa: E402
_REGISTERED = (airslots_model, batteries_model, battery_logs_model,
               reserves_model, switchcards_model)
assert _REGISTERED

# 测试库允许写锁等待并启用 WAL，便于用线程模拟并发发卡（生产为 MySQL 行锁）。
if db.DATABASE_URL.startswith('sqlite'):
    from sqlalchemy import event  # noqa: E402

    db.engine = create_engine(db.DATABASE_URL, connect_args={'timeout': 15})

    @event.listens_for(db.engine, 'connect')
    def _sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=15000')
        cursor.close()

from core.db import metadata  # noqa: E402,F401


def reset_db():
    metadata.drop_all(db.engine)
    metadata.create_all(db.engine)
    with db.engine.begin() as conn:
        # SQLite 外键开关随连接生效
        conn.execute(text('PRAGMA foreign_keys=ON'))
