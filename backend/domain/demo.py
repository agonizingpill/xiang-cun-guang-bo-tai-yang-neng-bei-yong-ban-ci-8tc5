from domain.airslots_model import airslots
from domain.batteries_model import batteries
from domain.battery_logs_model import battery_logs
from domain.reserves_model import reserves
from domain.switchcards_model import switchcards


def _two_day_logs():
    """BAT-04 两日内 48 个整点审签读数：含昼夜起伏与晴阴扰动。"""
    cloudy_hours = {5, 10, 15, 20, 25, 30, 35, 40, 45}
    rows = []
    for hour in range(48):
        clear = hour not in cloudy_hours
        load = 90.0
        if 16 <= hour % 24 <= 23:
            load += 45.0
        if hour % 24 in (21, 42):
            load += 18.0
        if not clear:
            load -= 9.0
        if hour % 24 in (7, 14, 28, 35):
            load += 18.0
        rows.append({'code': f'WH-{hour:02d}', 'meter': 'BAT-04', 'hour': hour,
                     'load_wh': round(load, 1), 'clear': clear, 'verified': True})
    return rows


FIXTURES = [
    (batteries, [
        {'code': 'BAT-04', 'meter': 'BAT-04', 'shift_hours': 3, 'capacity_wh': 2200.0,
         'margin_wh': 8.1},
    ]),
    (airslots, [
        {'code': 'AIR-17', 'title': '晚间村讯', 'hour': 18, 'battery': 'BAT-04',
         'license': '本地插播', 'offline': True},
        {'code': 'AIR-08', 'title': '田间校时', 'hour': 8, 'battery': 'BAT-04',
         'license': '台外联播', 'offline': False},
    ]),
    (battery_logs, _two_day_logs()),
    (reserves, [
        # prediction_wh / mae 与种子电池的整班（3 小时）口径一致。
        {'code': 'RV-00', 'airslot': 'AIR-08', 'meter': 'BAT-04', 'prediction_wh': 270.0,
         'plan_wh': 278.1, 'fallback': '受控中继', 'mae': 8.1, 'token': 'RV-SEED'},
    ]),
    (switchcards, [
        {'code': 'SW-00', 'reserve': 'RV-00', 'source': '本地时钟',
         'approved_wh': 280.0, 'state': '值守签发'},
    ]),
]
