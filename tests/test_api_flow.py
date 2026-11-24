"""端到端 API 测试：登录 → 登记电池 → 预测发卡 → 看板 → 撤卡/交接。"""
import json

import pytest
from fastapi.testclient import TestClient

import harness

# lifespan 会走 seed，先确保环境变量就绪再导入 app。
harness  # noqa: B018
from core.app import app  # noqa: E402
from core import queueing  # noqa: E402
from domain.learning import calculate  # noqa: E402
from scripts.seed_demo import seed  # noqa: E402


def _drain_compute():
    """同步执行排队中的计算任务，替代独立 worker 进程。"""
    items = queueing.broker.lrange('compute_requests', 0, -1)
    for item in items:
        job = json.loads(item)
        queueing.broker.set(
            f"compute:{job['token']}",
            json.dumps({'owner': job['owner'], 'input': job['input'], 'status': 'ready',
                        'result': calculate(job['input'])}))
        queueing.broker.lrem('compute_requests', 1, item)


@pytest.fixture()
def client():
    harness.reset_db()
    seed()
    with TestClient(app) as c:
        yield c


def _login(client, role):
    resp = client.post('/auth/login', json={'email': f'{role}@demo.test',
                                            'password': 'DemoC0de!2026'})
    assert resp.status_code == 200
    return {'Authorization': 'Bearer ' + resp.json()['token']}


def test_health_and_seed(client):
    auth = _login(client, 'viewer')
    assert client.get('/health').json() == {'ok': True}
    batteries = client.get('/batteries', headers=auth).json()
    assert {b['code'] for b in batteries} == {'BAT-04'}
    slots = client.get('/airslots', headers=auth).json()
    assert {s['battery'] for s in slots} == {'BAT-04'}


def test_full_flow_issue_board_withdraw_handover(client):
    reviewer = _login(client, 'reviewer')
    operator = _login(client, 'operator')

    #  viewer 不能发卡
    assert client.post('/switchcards/issue-switch',
                       headers=_login(client, 'viewer'),
                       json={'code': 'X', 'reserve': 'RV-00', 'source': '本地时钟',
                             'approved_wh': 999}).status_code == 403

    # 种子卡占额中；看板应给出各档已锁与可分
    board = client.get('/switchcards/board', headers=reviewer).json()
    assert len(board) == 1
    entry = board[0]
    assert entry['locked_wh'] == pytest.approx(280.0)
    assert entry['allocatable_wh'] == pytest.approx(
        entry['capacity_wh'] - entry['margin_wh'] - entry['locked_wh'])
    slot_codes = {s['airslot'] for s in entry['slots']}
    assert slot_codes == {'AIR-17', 'AIR-08'}

    # 新预测一轮：forecast → worker 同步出结果 → save-reserve
    queued = client.post('/reserves/forecast-wh', headers=operator,
                         json={'airslot': 'AIR-17', 'meter': 'BAT-04', 'clear': True})
    assert queued.status_code == 200
    token = queued.json()['token']
    _drain_compute()
    compute = client.get(f'/compute/{token}', headers=operator).json()
    assert compute['status'] == 'ready'
    saved = client.post('/reserves/save-reserve', headers=reviewer,
                        json={'code': 'RV-17', 'token': token})
    assert saved.status_code == 200, saved.text
    prediction = saved.json()['prediction_wh']
    assert saved.json()['plan_wh'] == pytest.approx(
        prediction + saved.json()['mae'])

    # 跨电表预测被拒
    bad = client.post('/reserves/forecast-wh', headers=operator,
                      json={'airslot': 'AIR-17', 'meter': 'BAT-99', 'clear': True})
    assert bad.status_code == 409

    # 发卡：低于预测必拒
    too_small = client.post('/switchcards/issue-switch', headers=reviewer,
                            json={'code': 'SW-17', 'reserve': 'RV-17',
                                  'source': '本地时钟', 'approved_wh': prediction - 1})
    assert too_small.status_code == 409 and '覆盖该档预测' in too_small.json()['detail']

    # 正常发卡
    ok = client.post('/switchcards/issue-switch', headers=reviewer,
                     json={'code': 'SW-17', 'reserve': 'RV-17',
                           'source': '本地时钟', 'approved_wh': prediction})
    assert ok.status_code == 200, ok.text

    # 撤卡重试幂等：只退一次
    w1 = client.post('/switchcards/withdraw', headers=reviewer, json={'card': 'SW-17'})
    assert w1.json()['refunded_wh'] == pytest.approx(prediction)
    w2 = client.post('/switchcards/withdraw', headers=reviewer, json={'card': 'SW-17'})
    assert w2.json()['idempotent'] is True and w2.json()['refunded_wh'] == 0

    # 已交接的卡仍占额，且撤卡被拒
    hand = client.post('/switchcards/handover', headers=operator,
                       json={'card': 'SW-00', 'note': 'WR-77 闭台交接'})
    assert hand.status_code == 200
    blocked = client.post('/switchcards/withdraw', headers=reviewer,
                          json={'card': 'SW-00'})
    assert blocked.status_code == 409 and '交接' in blocked.json()['detail']
    board2 = client.get('/switchcards/board', headers=reviewer).json()[0]
    assert board2['locked_wh'] == pytest.approx(280.0)  # SW-17 已撤，SW-00 仍占

    # 撤过的卡不能再交接
    late = client.post('/switchcards/handover', headers=operator,
                       json={'card': 'SW-17', 'note': 'WR-78'})
    assert late.status_code == 409


def test_offline_slot_rejects_external_clock(client):
    reviewer = _login(client, 'reviewer')
    operator = _login(client, 'operator')
    # 先为版权离线档 AIR-17 生成一张评估
    token = client.post('/reserves/forecast-wh', headers=operator,
                        json={'airslot': 'AIR-17', 'meter': 'BAT-04', 'clear': True}
                        ).json()['token']
    _drain_compute()
    assert client.post('/reserves/save-reserve', headers=reviewer,
                       json={'code': 'RV-17X', 'token': token}).status_code == 200
    # AIR-17 是版权离线档，台外校时必须被拦
    resp = client.post('/switchcards/issue-switch', headers=reviewer,
                       json={'code': 'SW-X', 'reserve': 'RV-17X',
                             'source': '台外校时', 'approved_wh': 999})
    assert resp.status_code == 409 and '本地时钟' in resp.json()['detail']
