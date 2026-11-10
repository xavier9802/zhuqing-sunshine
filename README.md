# 追晴 · 四川盆地日照预测

追晴（Sunshine Forecast）专注四川盆地日照变化，寻找「下一次什么时候能真正见到太阳」。

> 当前为 MVP 工程阶段。预测数据必须来自可追溯的模型预报批次；没有完成真实数据接入和实测验证前，不展示虚构预测或准确率。

## 技术栈

- Web：Next.js、React、TypeScript
- API：Python、FastAPI、Pydantic
- Worker：Python、httpx、SQLAlchemy、Shapely、PyProj
- Database：PostgreSQL + PostGIS
- Forecast source：Open-Meteo ECMWF IFS / AIFS
- Geography：USGS basin polygon proxy + GeoNames city points
- Local development：Docker Compose

## 本地启动

需要 Node.js 22+、npm 10+、Python 3.12+、Docker。

\`\`\`bash
cp .env.example .env
docker compose up --build -d db api web
\`\`\`

- Web：http://localhost:3000
- API 文档：http://localhost:8000/docs
- API 健康检查：http://localhost:8000/health

### 导入地理数据

\`\`\`bash
docker compose run --rm worker import-geography
\`\`\`

该任务会下载 USGS 盆地结构沉积边界、GeoNames 城市点，并生成可配置的 0.25° 裁剪网格，写入 PostGIS。

### 采集一次模型预报

\`\`\`bash
docker compose run --rm worker ingest-once --days 7
\`\`\`

默认模型：IFS HRES、IFS 0.25°、AIFS Single。每个模型单独请求、单独存档。

## Open-Meteo 使用授权

免费 API 仅限非商业使用。若追晴用于商业产品或商业推广，必须先配置合适的商业 API 计划：

\`\`\`env
OPEN_METEO_USAGE=commercial
OPEN_METEO_API_KEY=your-paid-api-key
\`\`\`

Worker 会自动切换到 \`customer-api.open-meteo.com\`。不要将免费接口用于商业部署。

## 关键数据原则

1. 每轮模型预报单独存档，禁止新数据覆盖历史预测。
2. 分开记录模型初始化、数据可用、抓取时间和预测有效时间。
3. 保留模型原生时间分辨率，并标记插值小时值。
4. 缺失值保持 NULL，不能静默填零。
5. 保留原始响应、SHA-256 和供应商实际解析到的网格坐标。
6. 模型一致性不等于经过校准的概率。
7. 四川盆地首期边界采用 USGS 结构沉积盆地数据作为概化代理，不宣称为官方行政或精细地貌边界。

项目架构、数据源和进度见 \`docs/\`。
