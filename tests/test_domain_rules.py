"""核心规则测试：整班 MAE、发卡额度、并发不超额、撤卡幂退、交接占额、看板。"""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import harness
from core.db import transaction
from core import queueing
from domain import batteries_service, reserves_service, switchcards_service
from domain.airslots_model import airslots
from domain.batteries_model import batteries
from domain.battery_logs_model import battery_logs
from domain.learning import HELD_OUT_HOURS, calculate, shift_window_mae, _fit
from domain.reserves_model import reserves
from domain.switchcards_model import switchcards

REVIEWER = {'sub': 'reviewer@demo.test', 'role': 'reviewer'}
OPERATOR = {'sub': 'operator@demo.test', 'role': 'operator'}


class _Schema:
    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)

    def model_dump(self):
        return dict(self.__dict__)


@pytest.fixture(autouse=True)
def fresh_db():
    harness.reset_db()
    yield


def _seed_battery(shift=3, capacity=1000.0, margin=0.0):
    with transaction() as conn:
        batteries_service.register_battery(
            conn, REVIEWER,
            _Schema(code='BAT-1', meter='M-1', shift_hours=shift, capacity_wh=capacity))
        if margin:
            conn.execute(batteries.update().where(batteries.c.code == 'BAT-1')
                         .values(margin_wh=margin))
        conn.execute(airslots.insert().values(code='AIR-A', title='甲档', hour=8,
                                              battery='BAT-1', license='本地', offline=False))
        conn.execute(airslots.insert().values(code='AIR-B', title='乙档', hour=18,
                                              battery='BAT-1', license='本地', offline=True))


def _seed_logs(meter='M-1', n=40):
    with transaction() as conn:
        existing = {row['hour'] for row in conn.execute(
            select(battery_logs.c.hour).where(battery_logs.c.meter == meter)).mappings()}
        for hour in range(n):
            if hour in existing:
                continue
            load = 100.0 + 10.0 * ((hour % 24) // 8)
            conn.execute(battery_logs.insert().values(
                code=f'W-{meter}-{hour}', meter=meter, hour=hour,
                load_wh=load, clear=True, verified=True))


def _forecast_and_save(airslot, code):
    _seed_logs()
    with transaction() as conn:
        queued = reserves_service.forecast_wh(
            conn, OPERATOR, _Schema(airslot=airslot, meter='M-1', clear=True))
    # 同步执行排队计算，替代独立 worker 进程
    item = queueing.broker.lrange('compute_requests', 0, -1)[0]
    job = json.loads(item)
    queueing.broker.set(f"compute:{job['token']}",
                        json.dumps({'owner': job['owner'], 'input': job['input'],
                                    'status': 'ready', 'result': calculate(job['input'])}))
    queueing.broker.lrem('compute_requests', 1, item)
    with transaction() as conn:
        return reserves_service.save_reserve(
            conn, REVIEWER, _Schema(code=code, token=queued['token']))


# ---------- 学习算子：整班预测 + 等长时窗整班 MAE ----------

def test_calculate_uses_equal_length_shift_windows():
    rows = [{'hour': h, 'load_wh': 100.0 + (h % 3), 'clear': True} for h in range(40)]
    out = calculate({'rows': rows, 'clear': True,
                     'window': {'code': 'AIR-A', 'hour': 8, 'shift_hours': 3}})
    # 留出 6 小时、整班 3 小时 → 两个完整等长时窗
    assert out['held_out'] == HELD_OUT_HOURS
    assert out['shift_windows'] == 2
    assert out['shift_hours'] == 3
    assert out['prediction_wh'] >= 0
    assert out['plan_wh'] == pytest.approx(out['prediction_wh'] + out['mae'])
    assert len(out['target_hours']) == 3

    # 手工复算等长时窗整班 MAE
    model = _fit(rows[:-6])
    mae, windows = shift_window_mae(model, rows[-6:], 3)
    assert windows == 2
    assert out['mae'] == pytest.approx(round(mae, 3))


def test_partial_tail_window_excluded():
    rows = [{'hour': h, 'load_wh': 90.0, 'clear': True} for h in range(40)]
    # shift=4：6 小时留出段只含 1 个完整时窗，末尾 2 小时零头不计
    out = calculate({'rows': rows, 'clear': True,
                     'window': {'code': 'AIR-A', 'hour': 8, 'shift_hours': 4}})
    assert out['shift_windows'] == 1


# ---------- 发卡：覆盖预测、扣公用余量、并发不超额 ----------

def test_issue_must_cover_prediction():
    _seed_battery()
    reserve = _forecast_and_save('AIR-A', 'RV-A')
    with transaction() as conn, pytest.raises(HTTPException) as exc:
        switchcards_service.issue_switch(
            conn, REVIEWER,
            _Schema(code='SW-1', reserve='RV-A', source='本地时钟',
                    approved_wh=reserve['prediction_wh'] - 1))
    assert '覆盖该档预测' in exc.value.detail


def test_issue_reserves_shared_margin_and_capacity():
    _seed_battery(capacity=1000.0, margin=100.0)
    reserve_a = _forecast_and_save('AIR-A', 'RV-A')
    _forecast_and_save('AIR-B', 'RV-B')
    with transaction() as conn:
        # 保存评估会用整班 MAE 刷新电池公用余量（这里取刷新后的真实值）。
        margin = conn.execute(select(batteries.c.margin_wh).where(
            batteries.c.code == 'BAT-1')).scalar_one()
        # 容量 1000，扣公用余量后可分 1000 - margin
        switchcards_service.issue_switch(
            conn, REVIEWER,
            _Schema(code='SW-A', reserve='RV-A', source='本地时钟',
                    approved_wh=reserve_a['prediction_wh']))
        board = switchcards_service.board(conn)
    entry = board[0]
    assert entry['margin_wh'] == pytest.approx(margin)
    assert entry['locked_wh'] == pytest.approx(reserve_a['prediction_wh'])
    assert entry['allocatable_wh'] == pytest.approx(
        1000.0 - margin - reserve_a['prediction_wh'])

    with transaction() as conn, pytest.raises(HTTPException) as exc:
        switchcards_service.issue_switch(
            conn, REVIEWER,
            _Schema(code='SW-BIG', reserve='RV-B', source='本地时钟',
                    approved_wh=1000.0 - margin + 1))
    assert '超额' in exc.value.detail


def test_concurrent_issues_never_oversell():
    # 说明：MySQL 生产路径在 issue_switch 内以 with_for_update() 锁定电池行，
    # 并发请求按行锁串行化，余额在同一事务内复查（见 switchcards_service.issue_switch）。
    # SQLite 不支持行锁语义，这里用「同一起点的交错申请」验证额度算术与拒绝路径：
    # 容量 1000，三张卡各要 ask，最多成交两张，第三张必被拒且总锁额不超容量。
    _seed_battery(capacity=1000.0, margin=0.0)
    reserve_a = _forecast_and_save('AIR-A', 'RV-A')
    reserve_b = _forecast_and_save('AIR-B', 'RV-B')
    reserve_a2 = _forecast_and_save('AIR-A', 'RV-A2')
    ask = max(reserve_a['prediction_wh'], reserve_b['prediction_wh'],
              reserve_a2['prediction_wh'])
    assert 2 * ask <= 1000.0 < 3 * ask

    outcomes = []
    for reserve_code, idx in [('RV-A', 'T1'), ('RV-B', 'T2'), ('RV-A2', 'T3')]:
        try:
            with transaction() as conn:
                switchcards_service.issue_switch(
                    conn, REVIEWER,
                    _Schema(code=idx, reserve=reserve_code, source='本地时钟',
                            approved_wh=ask))
            outcomes.append('ok')
        except HTTPException as exc:
            assert '超额' in exc.detail
            outcomes.append('reject')
    assert outcomes == ['ok', 'ok', 'reject']
    with transaction() as conn:
        board = switchcards_service.board(conn)[0]
    assert board['locked_wh'] == pytest.approx(2 * ask)
    # 评估保存会把整班 MAE 写入公用余量，可分 = 容量 - 公用余量 - 已锁。
    assert board['allocatable_wh'] == pytest.approx(
        1000.0 - board['margin_wh'] - 2 * ask)


def test_issue_switch_locks_battery_row_for_serialization():
    # 静态保证：发卡路径必须对电池行加行锁（get(lock=True) → SELECT ... FOR UPDATE），
    # 否则并发事务会读到同一余额而双花。
    import inspect

    source = inspect.getsource(switchcards_service.issue_switch)
    assert "get(conn, batteries, slot['battery'], lock=True)" in source
    assert inspect.getsource(switchcards_service.get).find('with_for_update') >= 0


# ---------- 撤卡：先办成原则、幂等不重复退、交接仍占额 ----------

def _one_card(code='SW-1', reserve='RV-A', approved=None, state=None):
    if approved is None:
        with transaction() as conn:
            approved = conn.execute(select(reserves.c.prediction_wh).where(
                reserves.c.code == reserve)).scalar_one()
    with transaction() as conn:
        switchcards_service.issue_switch(
            conn, REVIEWER,
            _Schema(code=code, reserve=reserve, source='本地时钟', approved_wh=approved))
        if state:
            conn.execute(switchcards.update().where(switchcards.c.code == code)
                         .values(state=state))


def test_withdraw_refunds_once_and_is_idempotent():
    _seed_battery(capacity=1000.0)
    reserve = _forecast_and_save('AIR-A', 'RV-A')
    _one_card()
    with transaction() as conn:
        first = switchcards_service.withdraw(conn, REVIEWER, _Schema(card='SW-1'))
        again = switchcards_service.withdraw(conn, REVIEWER, _Schema(card='SW-1'))
        board = switchcards_service.board(conn)
    assert first['refunded_wh'] == pytest.approx(reserve['prediction_wh'])
    assert first['idempotent'] is False
    assert again['refunded_wh'] == 0 and again['idempotent'] is True
    assert board[0]['locked_wh'] == 0.0


def test_handover_blocks_withdraw_and_keeps_quota():
    _seed_battery(capacity=1000.0)
    reserve = _forecast_and_save('AIR-A', 'RV-A')
    _one_card()
    with transaction() as conn:
        switchcards_service.handover(conn, OPERATOR, _Schema(card='SW-1', note='WR-77 闭台'))
        with pytest.raises(HTTPException) as exc:
            switchcards_service.withdraw(conn, REVIEWER, _Schema(card='SW-1'))
        assert '交接' in exc.value.detail
        board = switchcards_service.board(conn)
    # 已交接仍占额
    assert board[0]['locked_wh'] == pytest.approx(reserve['prediction_wh'])
    with transaction() as conn:
        card = conn.execute(
            select(switchcards).where(switchcards.c.code == 'SW-1')).mappings().one()
    assert card['state'].startswith('已闭台')


def test_withdraw_blocks_late_handover():
    _seed_battery(capacity=1000.0)
    _forecast_and_save('AIR-A', 'RV-A')
    _one_card()
    with transaction() as conn:
        switchcards_service.withdraw(conn, REVIEWER, _Schema(card='SW-1'))
        with pytest.raises(HTTPException) as exc:
            switchcards_service.handover(conn, OPERATOR,
                                         _Schema(card='SW-1', note='WR-78 闭台'))
        assert '交接或已撤卡' in exc.value.detail


# ---------- 看板：各档已锁与还能分多少 ----------

def test_board_lists_per_slot_locked_and_predictions():
    _seed_battery(capacity=1200.0, margin=50.0)
    reserve_a = _forecast_and_save('AIR-A', 'RV-A')
    _forecast_and_save('AIR-B', 'RV-B')
    _one_card(code='SW-A', reserve='RV-A', approved=reserve_a['prediction_wh'])
    with transaction() as conn:
        board = switchcards_service.board(conn)[0]
        margin = conn.execute(select(batteries.c.margin_wh).where(
            batteries.c.code == 'BAT-1')).scalar_one()
    by_slot = {row['airslot']: row for row in board['slots']}
    assert by_slot['AIR-A']['locked_wh'] == pytest.approx(reserve_a['prediction_wh'])
    assert by_slot['AIR-B']['locked_wh'] == 0.0
    assert by_slot['AIR-A']['prediction_wh'] == pytest.approx(reserve_a['prediction_wh'])
    assert board['allocatable_wh'] == pytest.approx(
        1200.0 - margin - reserve_a['prediction_wh'])
