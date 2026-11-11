# 追晴 · 四川盆地日照预测

> 下一次太阳，什么时候来？

追晴（Sunshine Forecast）是面向四川盆地的非商业日照预测实验站点。目标生产架构为 **Next.js 静态网站托管 + Python 3.11 CloudBase 定时云函数 + PG 模式云存储**。气象算法仍由现有 Python 代码驱动，不引入常驻服务器、Redis 或业务数据库。GitHub Pages 保留为可手动启用的回滚站点。

## 版本状态

当前正式版本：**V1.2.0**（2026-11-10）。已合并至 main，并完成 GitHub Pages 生产部署。

## 立即查看

GitHub Pages **预期**网址：

https://xavier9802.github.io/zhuqing-sunshine/

只有在本分支合并至默认分支、并在仓库 Settings → Pages 选择 **GitHub Actions** 发布源、部署成功后，这个网址才会真实上线。

## 核心功能

- 四川盆地 0.25° 网格，USGS 概化盆地边界裁剪，按实际面积加权。
- 未来 72 小时的逐小时网格日照图层与区域覆盖率。
- 未来 7 天区域日照时长趋势。
- 14 个城市的连续日照窗口与逐小时预测详情。
- 三种 ECMWF 模式：IFS HRES、IFS 0.25°、AIFS 0.25°（分别获取与标记）。
- V1.1 晴好判定联合总云/低云/中高云、日照、降水、湿度、短波辐射、白昼时段和（HRES）能见度；多模型等权投票，显示方向一致性而非概率。
- 显示模型初始化、预测有效时次、采集时间、插值时次与来源。
- 缺失模型时显示缺失或降级状态，绝不产生伪造的放晴概率或预测数值。

天气数据由 CloudBase 定时云函数采集、计算并发布为版本化 JSON 快照；打开网页的用户**不会直接访问 Open-Meteo**。CloudBase 前端先读取 `zhuqing/latest.json`，再加载对应版本的不可变数据文件。

## 仓库结构

| 位置 | 用途 |
|---|---|
| apps/web/ | Next.js 15 静态页面、城市详情、MapLibre |
| sitegen/ | Python 天气采集、地理数据、日照计算和 JSON 快照生成 |
| sitegen/tests/ | 单元测试与无网络数据生成测试 |
| .github/workflows/ci.yml | 静态网站、Python 与 TypeScript 自动测试 |
| .github/workflows/pages.yml | 每 4 小时尝试刷新并发布 GitHub Pages |
| docs/ | 架构、气象来源、上线清单 |

**没有在线数据库。** USGS 网格几何只保存一份，逐时预测只保存对应的网格数值数组，不重复存储多套 GeoJSON。

## 本地开发

需 Node.js 22+、Python 3.12+，以及 npm。

\`\`\`bash
git clone -b main https://github.com/xavier9802/zhuqing-sunshine.git
cd zhuqing-sunshine
python3 -m pip install -r sitegen/requirements.txt
npm install

# 生成明确标记为“尚无真实数据”的静态结构（不生成模拟预报）
python3 -m sitegen.build --mode placeholder

npm run dev:web
\`\`\`

浏览器打开 http://localhost:3000。

本地采集真实天气数据：

\`\`\`bash
python3 -m sitegen.build --mode live --require-live
npm run dev:web
\`\`\`

若全部天气模型无法访问，采集程序会返回错误，不允许以虚构数据代替。若只是要测试静态构建：

\`\`\`bash
python3 -m pytest -q sitegen/tests
NEXT_PUBLIC_BASE_PATH=/zhuqing-sunshine npm run build:web
\`\`\`

构建后的完整静态网站位于 apps/web/out/。

## CloudBase 自动更新

CloudBase 生产部署配置位于：

- `.github/workflows/cloudbase.yml` — GitHub Actions 构建并部署 CloudBase 云函数与静态网站；
- `cloudbaserc.json` — Python 3.11 云函数、900 秒超时、3072 MB 内存和四小时定时触发器；
- `functions/zhuqingForecastRefresh/` — 完整三模型采集、预测计算和快照发布入口；
- `sitegen/cloudbase_storage.py` — PG 模式 CloudBase Storage 上传、版本切换和旧快照清理；
- `cloudbase/sql/001_zhuqing_data_bucket.sql` — 创建公开只读的 `zhuqing-data` Bucket。

CloudBase 定时触发器每 4 小时触发一次（七字段 Cron：`0 17 */4 * * * *`）。每轮先生成完整快照，再上传版本化文件，最后更新 `zhuqing/latest.json`；如果全部模型失败，不切换版本，继续保留上次成功数据。正常只保留最近两份完整快照。

首次部署前需要配置 GitHub Actions Variables / Secrets，并按 [CloudBase 部署指南](docs/CLOUDBASE_DEPLOYMENT.md) 设置 PG Storage 公共读取与 CORS。CloudBase 环境未配置时，GitHub Pages 仍按原方式运行；配置 `CLOUDBASE_ENV_ID` 与存储公开 URL 后，GitHub Pages 自动停止重复采集。必要时可在 Pages 工作流手动选择 `force_github_pages` 回滚。

本地开发、历史回测与 GitHub Actions CI 仍保留；算法代码不因部署平台迁移而重写。

## 使用范围及数据风险

- 初期采用 Open-Meteo **非商业**接口，不能无授权用于商业用途；GitHub Pages 也不适合做商业 SaaS。
- 天气来自 ECMWF 数值模式，计算出的晴好分类是透明的产品规则，不是气象部门官方晴天定义；三个 ECMWF 模型并非独立预报中心，投票不等于统计概率。
- 源数据的空间/时间分辨率因模型而异，部分小时结果是服务端插值值。
- USGS 数据是 1:5,000,000 结构沉积盆地概化边界，不代表精确地形或行政边界；其原始数据缺少 .prj，WGS84 为临时展示假设。
- GitHub Pages、OpenStreetMap 地图瓦片对中国大陆访问的稳定性不能保证。
- 已建立 NOAA GHCNh 机场/地面站历史验证与 NASA POWER 短波辐射对照；当前只有 3 个可用云况观测站，216 个站点日样本，尚未达到四站门槛，结果仍属探索性验证。
- NASA POWER 是卫星/再分析辐射参考产品，不是地面日照时数仪器；**不展示未经验证的预测准确率或校准概率**。

来源：[Open-Meteo](https://open-meteo.com/) · [GeoNames](https://www.geonames.org/)（CC BY 4.0）· [USGS OFR 00-047](https://pubs.usgs.gov/of/2000/of00-047/) · © OpenStreetMap contributors。


## 历史预报回测

运行 python -m sitegen.backtest，使用 NOAA NCEI GHCNh 地面站逐时报文与 Open-Meteo 历史 ECMWF IFS HRES 单次预报进行逐站、逐日、1–3 天提前量验证。报告输出混淆矩阵、晴/晴间多云识别 precision/recall/F1，以及云量 MAE 和偏差。该数据是机场/地面站云况代理，不是日照时数传感器；样本不足时不得据此调整生产阈值或宣传预测准确率。详细口径见 docs/FORECAST_BACKTEST.md。


## V1.2 验证进展

- 24 批次 ECMWF IFS HRES 历史预报；12 个候选站点中，3 个机场站具备足够的云况观测，形成 216 个站点日样本。
- 另有 12 个空间点位用于 NASA POWER 日太阳辐射对照，并按 2024–2025 训练、2026 时间外留出评估辐射偏差稳定性。
- 专项全盆地 HRES 质量 smoke 已通过：ECMWF IFS HRES 覆盖 372 个位置（358 个网格、14 个城市），输出 72 小时预报；另在 2026-11-10 14:00（北京时间）的 GitHub Pages 生产快照中，IFS HRES、IFS 0.25°、AIFS 0.25° 三个模型均成功覆盖 372 个位置，预报延伸至 2026-11-17 13:00（北京时间）。
- 由于可用云况观测站不足，V1.2 不会据此擅自修改生产晴天阈值，也不会把辐射订正研究结果自动应用于线上预测。
- 详见 [历史验证协议](docs/FORECAST_BACKTEST.md)。
