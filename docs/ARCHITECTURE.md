# Architecture

```text
Open-Meteo
    |
    v
Worker (scheduled ingestion / normalization / sunshine processing)
    |
    +----> Raw provider payload archive
    |
    v
PostgreSQL + PostGIS
    |
    v
FastAPI
    |
    v
Next.js web application
```

## Responsibilities
- Web：展示、地图交互、城市查询和预测解释。
- API：稳定的产品查询接口；浏览器不直接请求气象服务商。
- Worker：模型批次检测、数据采集、标准化、日照计算和验证。
- PostGIS：盆地边界、城市点位和空间网格。
- Redis：后续按缓存和队列需求增加，非首期必需。

## Engineering rules
1. 每轮预报单独存档，不覆盖历史数据。
2. 分开记录模型初始化、抓取、预测有效时间和预报提前量。
3. 每条序列记录模型名称及原生时间分辨率。
4. 区分观测值、模型值和派生指标。
5. 缺失值保持缺失，不能静默填零。
6. API 返回数据新鲜度和处理状态。
7. 模型一致性不能称为校准概率。

## MVP deployment
Docker Compose 启动 PostGIS、FastAPI 和 Next.js。数据采集 worker 在 provider adapter 完成后作为独立任务服务加入。
