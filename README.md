# 追晴 · 四川盆地日照预测

追晴（Sunshine Forecast）关注四川盆地日照变化，回答一个简单的问题：**下一次什么时候更有机会见到太阳？**

当前版本是可本地启动的 MVP。系统以可追溯的数值天气预报批次为基础，计算区域日照覆盖、连续日照窗口与城市级日照趋势。没有地面站点验证前，不展示虚构的预测准确率或未经校准的概率。

## MVP 功能

- 四川盆地概化边界与 0.25° 裁剪网格，按网格实际面积加权。
- 成都、重庆及周边 12 个重点城市的地理点位。
- ECMWF IFS HRES、IFS 0.25°、AIFS Single 三个模型独立存档和切换。
- 模型初始化时间、数据可用时间、采集时间、预报有效时间分开记录。
- 原始响应与 SHA-256 留档，保留模型原生时间步长并标记插值时次。
- 盆地日照分布地图、72 小时时间轴、未来 7 日日照趋势。
- 城市详情、连续日照窗口和逐小时预报。
- Worker 每小时轮询模型批次；同一模型初始化及修订版本不重复采集。
- Docker Compose 一键启动，FastAPI 文档与健康检查。

## 技术栈

| 层 | 技术 |
|---|---|
| Web | Next.js、React、TypeScript、MapLibre GL |
| API | Python、FastAPI、Pydantic |
| Worker | Python、httpx、SQLAlchemy、Shapely、PyProj |
| Database | PostgreSQL 16 + PostGIS |
| Weather | Open-Meteo ECMWF Single Runs API |
| Geography | USGS basin boundary proxy、GeoNames |
| Runtime | Docker Compose |

## 本地启动

需要 Docker Desktop / Docker Engine、Docker Compose 和 Make。

\`\`\`bash
git clone https://github.com/xavier9802/zhuqing-sunshine.git
cd zhuqing-sunshine
make start
\`\`\`

第一次启动会自动：
1. 从 \`.env.example\` 创建本地 \`.env\`（若尚不存在）。
2. 构建并启动 PostGIS、API 和 Web。
3. 下载并导入 USGS 盆地边界、GeoNames 城市点和网格。
4. 启动每小时轮询模型数据的 Worker。

启动地址：

- Web：http://localhost:3000
- API 文档：http://localhost:8000/docs
- API 健康检查：http://localhost:8000/health
- 数据库就绪检查：http://localhost:8000/health/ready

常用命令：

\`\`\`bash
make status   # 查看服务状态
make logs     # 查看 API / Web / Worker 日志
make down     # 停止服务，保留数据库卷
make rebuild  # 重新构建并启动
\`\`\`

也可以手动分步启动：

\`\`\`bash
cp .env.example .env
docker compose up --build -d db api web
docker compose run --rm worker import-geography
docker compose --profile jobs up --build -d worker
\`\`\`

首次地理数据导入完成后，Worker 会持续采集最新可用模型批次。也可以手动执行一次：

\`\`\`bash
docker compose run --rm worker ingest-once --days 7
\`\`\`

## 环境配置与数据授权

主要配置见 \`.env.example\`。

Open-Meteo 免费接口仅限非商业使用。个人原型评估可按其免费层条款使用；若追晴用于商业产品、商业推广或其他商业场景，须先购买适用的商业计划，并设置：

\`\`\`env
OPEN_METEO_USAGE=commercial
OPEN_METEO_API_KEY=your-paid-api-key
\`\`\`

Worker 将自动切换到 customer API 域名。不要把免费接口用于商业部署。详见 [Open-Meteo 使用条款](https://open-meteo.com/en/terms) 与 [价格及授权说明](https://open-meteo.com/en/pricing)。

## 数据来源与边界

- **气象预报**：[Open-Meteo](https://open-meteo.com/)；数据按 CC BY 4.0 提供。页面保留来源署名，追晴对原始预报进行网格聚合和日照指标计算。
- **城市坐标**：[GeoNames](https://www.geonames.org/)；CC BY 4.0。
- **盆地边界**：[USGS Open-File Report 00-047](https://pubs.usgs.gov/of/2000/of00-047/)；使用其结构沉积盆地数据作为概化代理。
- **地图底图**：© OpenStreetMap contributors。

USGS 原始边界是约 1:5,000,000 比例尺的结构沉积盆地概化数据，并非行政区划或精细地貌边界。其 Shapefile 缺少 \`.prj\`；USGS 元数据只明确经纬度十进制度，未明确大地基准。当前对地图展示临时采用 WGS84，并在数据元信息中保留这一假设，不能将其视为测绘级坐标依据。

## 日照计算口径

- 单个网格小时内预计有效日照不少于 30 分钟，计入有效日照覆盖。
- 盆地放晴窗口：连续至少 2 小时，盆地有效日照覆盖率不低于 50%，且数据完整度不低于 80%。
- 网格权重使用边界裁剪后的等积投影面积，不以经纬度格点数量简单平均。
- 缺失数据保持 NULL；不以零值补齐。
- 预报原生时间分辨率按模型 lead time 记录；高于小时步长的数据插值时次会显式标记。
- “日照窗口”是追晴的产品计算口径，不等同于气象部门的官方晴天定义。
- 模型预报不等于地面实况。尚未接入站点观测并完成回测前，不发布准确率、命中率或概率性承诺。

## 验证状态

GitHub Actions 持续执行 Python / API / Web 检查与 Docker 构建。地理数据集成测试会从真实来源下载并导入数据，在 PostGIS 中验证边界与网格几何，并核对城市数量。

当前已验证的地理快照：**14 个城市、358 个 0.25° 裁剪网格**。模型预报数据的实际采集和地面站点回测仍需在部署环境中完成。

## 项目结构

\`\`\`text
apps/web/          Next.js 前端
services/api/      FastAPI 查询接口
services/worker/   地理数据导入与模型预报采集
docs/              架构与开发任务
docker-compose.yml 本地服务编排
Makefile           一键启动与常用操作
\`\`\`
