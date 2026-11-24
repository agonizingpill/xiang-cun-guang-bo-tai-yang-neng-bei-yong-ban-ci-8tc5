# 乡村广播太阳能备用班次

岭声乡村广播的节目组和电源值守共用一张备播卡，在版权离线时段安排本地校时与蓄电余量。

## 现场工作与联系人

模拟客户为岭声乡村广播合作社。广播时刻表、蓄电日志、用量周期预测、备用机优先级；节目版权离线时段只能接本地时钟。

- 共用电池 `batteries`，字段为 `meter`（绑定电表）、`shift_hours`（整班小时）、`capacity_wh`（容量 Wh）、`margin_wh`（公用余量，整班 MAE Wh）。几档连播节目挂在同一电池下共用额度。模型约束位于 `backend/domain/batteries_model.py`，规则位于 `batteries_service.py`。
- 节目时段表 `airslots`，字段为 `title`（节目）、`hour`（起播小时）、`battery`（所属共用电池）、`license`（节目源许可）、`offline`（离线时段）。模型约束位于 `backend/domain/airslots_model.py`，规则位于 `airslots_service.py`。
- 蓄电班记与测量 `battery_logs`，字段为 `meter`（电表编号）、`hour`（两日内整点）、`load_wh`（用量 Wh）、`clear`（天空晴）、`verified`（抄表审核）。模型约束位于 `backend/domain/battery_logs_model.py`，规则位于 `battery_logs_service.py`。
- 备用分钟核算 `reserves`，字段为 `airslot`（节目时段）、`meter`（电表）、`prediction_wh`（整班点预测 Wh）、`plan_wh`（建议发卡 Wh = 点预测 + 整班 MAE）、`fallback`（备用源优先级）、`mae`（整班 MAE Wh）、`token`（计算号）。模型约束位于 `backend/domain/reserves_model.py`，规则位于 `reserves_service.py`。
- 班组备播卡 `switchcards`，字段为 `reserve`（备用评估）、`source`（实际时钟源）、`approved_wh`（锁定备用 Wh）、`state`（状态：值守签发 / 已撤卡 / 已闭台 WR-xx）。模型约束位于 `backend/domain/switchcards_model.py`，规则位于 `switchcards_service.py`。

团队为模拟的6 人广播合作社值守组，负责两个电源档位的备播。

值守员用节目表和电池抄数安排断电时段。周期负荷难从表格读出，漏掉一小时会扭曲拟合，离线版权段容易误选台外时钟。

节目时刻表和已签电量日志进入估计，接班人拿到有限额与时钟源的备用卡。

### 一天的业务操作

1. 07:00 确认 AIR-17 晚间村讯版权离线。
2. 08:00 班组登记 BAT-11 整点 88.4 Wh。
3. 09:00 核对 BAT-04 两日班记。
4. 11:20 用 24 小时 Fourier 基回测末 6 小时。
5. 15:00 签发 RV-24 备用电量评估。
6. 17:45 台外时钟请求被拦后改用本地时钟。
7. 22:10 持 WR-77 完成闭台交接。

## 启动

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

打开 `http://127.0.0.1:18317`。FastAPI OpenAPI 在 `http://127.0.0.1:19317/docs`。
Compose 运行 Nginx、Python FastAPI、独立 Redis 消费进程、SQL 数据库和 Redis，SQL 与 Redis 使用命名卷。
本机开发时，在 Python 3.11 环境安装 `backend/requirements.txt` 后从 backend 目录运行 `uvicorn core.app:app`。须提供 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`，`SEED_DEMO` 控制演示初始化。

| 演示账号 | 权限 |
|---|---|
| operator@demo.test | 提交领域记录和计算请求 |
| reviewer@demo.test | 提交记录并执行有业务约束的复核操作 |
| viewer@demo.test | 浏览业务台账 |

三个本地演示账号均使用 `DemoC0de!2026`。角色在 `backend/core/roles.py` 和 `frontend/src/store.js` 中声明。计算状态在 worker、queueing、API 和同一前端 store 中使用。

## 页面与接口

| 业务任务 | FastAPI 路由 | 页面 |
|---|---|---|
| 共用电池台账 | `/batteries` /batteries/register | `frontend/src/pages/batteries.js` |
| 节目时段表 | `/airslots` /airslots/mark-offline | `frontend/src/pages/airslots.js` |
| 蓄电班记与测量 | `/battery_logs` /battery_logs/log-charge，/battery_logs/approve-meter | `frontend/src/pages/battery_logs.js` |
| 备用分钟核算 | `/reserves` /reserves/forecast-wh，/reserves/save-reserve | `frontend/src/pages/reserves.js` |
| 班组备播卡 | `/switchcards` /switchcards/issue-switch，/switchcards/withdraw，/switchcards/handover | `frontend/src/pages/switchcards.js` |
| 备播额度看板 | `/switchcards/board` | `frontend/src/pages/board.js` |

SQL 实体与约束在 `backend/domain` 下维护。前端使用原生 ES modules。核心算子为 Fourier 基 + OLS：OLS 在训练时段拟合一、二阶谐波和晴天标记，对整班窗口逐小时截零预测并求和得到整班点预测；留出末 6 小时按与整班等长的不重叠时窗汇总，计算整班平均绝对误差（MAE）作为该电池的公用余量。建议发卡额 = 整班点预测 + 整班 MAE。

发卡规则：单卡锁定电量须覆盖该档整班点预测；同一电池下所有占额卡片（已签发、已交接）的锁定合计加上公用余量不得超过电池容量，发卡事务对电池行 `SELECT ... FOR UPDATE` 加锁，并发请求串行复查额度，绝不超额。撤卡把卡片置为已撤卡并释放额度，重复撤卡幂等不重复退；撤卡与交接撞车时认先办成的一方，已交接卡片拒绝撤卡且继续占额。`/switchcards/board` 按电池汇总容量、公用余量、已锁电量、还能分多少，并列出各档预测与已锁明细。

### 本地测试

无 Docker 环境时可用 SQLite + 内存假 Redis 跑规则与接口测试（不依赖外部服务）：

```sh
python -m pytest tests/ -q
```

按模拟广播班记推演。卡片供人工值守查阅，应用只处理纸本条件的数字记录。

[MIT](LICENSE)
