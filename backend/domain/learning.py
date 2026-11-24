from math import cos, pi, sin

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

# 留出段长度（小时）：末段不参与拟合，专门用于回测。
HELD_OUT_HOURS = 6


def design(hour, clear):
    angle = 2 * pi * hour / 24
    return [sin(angle), cos(angle), sin(2 * angle), cos(2 * angle), int(clear)]


def _fit(rows):
    model = LinearRegression()
    model.fit([design(x['hour'], x['clear']) for x in rows], [x['load_wh'] for x in rows])
    return model


def predict_hours(model, start_hour, shift_hours, clear):
    """整班窗口 [start_hour, start_hour + shift_hours) 逐小时截零预测之和。"""
    hours = [start_hour + offset for offset in range(shift_hours)]
    values = model.predict([design(hour, clear) for hour in hours])
    return [max(0.0, float(value)) for value in values], hours


def shift_window_mae(model, held, shift_hours):
    """留出段内按与整班等长的不重叠时窗汇总，计算整班平均绝对误差。

    只取完整时窗；末尾不足一个整班的零头不参与平均。
    """
    predicted = [max(0.0, float(y)) for y in model.predict(
        [design(x['hour'], x['clear']) for x in held])]
    actual = [float(x['load_wh']) for x in held]
    window_errors = []
    for start in range(0, len(held) - shift_hours + 1, shift_hours):
        end = start + shift_hours
        window_errors.append(abs(sum(actual[start:end]) - sum(predicted[start:end])))
    return sum(window_errors) / len(window_errors), len(window_errors)


def calculate(data):
    rows = data['rows']
    shift_hours = int(data['window']['shift_hours'])
    if not 1 <= shift_hours <= HELD_OUT_HOURS:
        raise ValueError(f'整班时长须在 1 到 {HELD_OUT_HOURS} 小时之间')
    train, held = rows[:-HELD_OUT_HOURS], rows[-HELD_OUT_HOURS:]
    model = _fit(train)

    # 留出段内逐小时 MAE（保留作拟合诊断），整班 MAE 用等长时窗汇总。
    hourly_predicted = model.predict([design(x['hour'], x['clear']) for x in held])
    hourly_mae = float(mean_absolute_error([x['load_wh'] for x in held], hourly_predicted))
    mae, windows = shift_window_mae(model, held, shift_hours)

    slot_hour = int(data['window']['hour'])
    shift_values, hours = predict_hours(model, slot_hour, shift_hours, data['clear'])
    prediction_wh = sum(shift_values)
    mae = round(mae, 3)
    prediction_wh = round(prediction_wh, 3)
    return {
        'mae': mae,
        'hourly_mae': round(hourly_mae, 3),
        'prediction_wh': prediction_wh,
        'plan_wh': round(prediction_wh + mae, 3),
        'held_out': len(held),
        'shift_windows': windows,
        'shift_hours': shift_hours,
        'target_hours': hours,
        'period': 24,
        'training': len(train),
    }
