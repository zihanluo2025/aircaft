# Turnaround

机场飞机清洁公司 leading hand 用的手机优先网站：排班、每架飞机的分工、用时、乘务签字、真实航班。

## 技术栈
- 前端：Vue 3 + Vite（`frontend/`），样式是纯 CSS 变量
- 后端：Python 3.11 + FastAPI + SQLAlchemy 2.0 + Pydantic v2（`backend/`）
- 数据库：本地 SQLite，线上 PostgreSQL（`DATABASE_URL`）
- 航班数据：FlightAware AeroAPI v4

## 常用命令
- 后端测试：`cd backend && python -m pytest`（不要直接用 `pytest`，会用到 conda 的）
- 启动后端：`make backend-dev`；启动前端：`make frontend-dev`
- 试 FlightAware：`cd backend && python -m scripts.check_flight_api --shift night --raw`

## 业务规则（不要改坏）
- Morning 和 Night 是两批完全不同的员工，数据和界面颜色都要严格分开。
- 排班由经理提前两周导入（Early / Late / All day）。当天的修改是"例外"，要能和原计划对比并一键恢复。
- Driver 和 Truck 需要资格，由 leading hand 每天指定人选；Toilet 谁都可以做。这三个岗位一天内固定。
- 其他岗位（Business、Vacuum、Economy 前中后）按每架飞机分配。
- 不能重复分配同一个人；只有当天在岗的人才能被分配；开始清洁时记录固定岗位的快照。
- 签字必须在清洁完成之后。

## 时间和班次（不要改坏）
- 系统时间一律使用南澳阿德莱德时间（`Australia/Adelaide`，有夏令时）。不要用服务器或浏览器所在时区做班次判断。数据库里的时间戳存 UTC，显示和班次判断时再转成阿德莱德时间。
- 早班 Morning：06:00 到 13:00。
- 晚班 Night：其余时间，即 13:00 到次日 06:00。凌晨 00:00-06:00 的航班算前一天的晚班。
- 对应配置：`MORNING_WINDOW=06:00-13:00`，`NIGHT_WINDOW=13:00-06:00`，`AIRPORT_TZ=Australia/Adelaide`。

## 航班数据
- 只保留国际航班（出发机场 ICAO 不以 Y 开头）加上 Jetstar（JQ）和 Virgin Australia（VA）。
- 同步绝不能修改已经开始清洁的航班，也不能动人员、备注和签字。
- 按结果集计费，注意 `FLIGHT_MONTHLY_CALL_LIMIT`。

## 约定
- 界面文字用英文，沟通和注释用中文都可以。
- 改完后端要跑 `python -m pytest`。
- 不要提交 `.env`。