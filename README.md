# 追晴 · 四川盆地日照预测

追晴（Sunshine Forecast）专注四川盆地日照变化，寻找「下一次什么时候能真正见到太阳」。

> 当前为 MVP 工程搭建阶段。尚未接入生产气象数据，不展示虚构的天气预测或准确率。

## 技术栈
- Web：Next.js、React、TypeScript
- API：Python、FastAPI、Pydantic
- Worker：Python、httpx
- Database：PostgreSQL + PostGIS
- Weather data：Open-Meteo（MVP 数据入口）
- Local development：Docker Compose

## 目录
- `apps/web`：Next.js 前端
- `services/api`：FastAPI 服务
- `services/worker`：气象数据采集与计算任务
- `packages/contracts`：前后端共享数据契约
- `docs`：产品与工程文档

## 本地启动
需要 Node.js 22+、npm 10+、Python 3.12+、Docker。

```bash
cp .env.example .env
docker compose up --build
```

- Web：http://localhost:3000
- API 文档：http://localhost:8000/docs
- API 健康检查：http://localhost:8000/health

单独运行前端：`npm install && npm run dev:web`。

运行 API 测试：
```bash
cd services/api
pip install -e ".[dev]"
pytest
```

## 数据原则
1. 每轮预报单独存档，禁止新数据覆盖历史预测。
2. 模型初始化时间、抓取时间、预测有效时间和预报提前量分开记录。
3. 区分模型原生时间分辨率与插值后的小时数据。
4. 模型一致性不等于经过校准的概率。
5. 没有可靠观测验证前，不展示准确率。
6. 公开服务前完成数据授权与气象信息服务合规审查。

项目进度见 [开发任务](docs/DEVELOPMENT-TASKS.md)。
