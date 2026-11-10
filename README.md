# 追晴 · 四川盆地日照预测

> 下一次太阳，什么时候来？

追晴（Sunshine Forecast）是面向四川盆地的非商业日照预测实验站点。采用 **Next.js 静态导出 + GitHub Actions 定时采集 + GitHub Pages**，没有常驻 API、PostgreSQL、PostGIS、Redis 或 Docker。

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

所有天气数据由 GitHub Actions 服务器采集；打开网页的用户**不会直接访问 Open-Meteo**。

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
git clone -b feature/github-pages-static-mvp https://github.com/xavier9802/zhuqing-sunshine.git
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

## GitHub Pages 自动更新

在 main 默认分支上，.github/workflows/pages.yml 会在这些时机执行：

- push 到 main；
- 在 Actions 页面手动运行；
- 每 4 小时在 UTC 分钟 17 尝试自动刷新。

每次成功生成的盆地与城市预报汇总另存为 GitHub Actions Artifact，保留14天用于短期核对，不存数据库或重复网格几何。定时任务在 GitHub Actions 不保证准点执行。若所有模型不可用，定时任务失败并保留上次成功发布的网站；页面必须结合其“数据采集时间”和模型时次判断新鲜度。

GitHub Pages 首次发布需要在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。详见 docs/ARCHITECTURE.md。

## 使用范围及数据风险

- 初期采用 Open-Meteo **非商业**接口，不能无授权用于商业用途；GitHub Pages 也不适合做商业 SaaS。
- 天气来自 ECMWF 数值模式，计算出的晴好分类是透明的产品规则，不是气象部门官方晴天定义；三个 ECMWF 模型并非独立预报中心，投票不等于统计概率。
- 源数据的空间/时间分辨率因模型而异，部分小时结果是服务端插值值。
- USGS 数据是 1:5,000,000 结构沉积盆地概化边界，不代表精确地形或行政边界；其原始数据缺少 .prj，WGS84 为临时展示假设。
- GitHub Pages、OpenStreetMap 地图瓦片对中国大陆访问的稳定性不能保证。
- 尚未对接地面观测站并完成回测，**不展示预测准确率或校准后的概率**。

来源：[Open-Meteo](https://open-meteo.com/) · [GeoNames](https://www.geonames.org/)（CC BY 4.0）· [USGS OFR 00-047](https://pubs.usgs.gov/of/2000/of00-047/) · © OpenStreetMap contributors。


## 历史预报回测

运行 python -m sitegen.backtest，使用 NOAA NCEI GHCNh 地面站逐时报文与 Open-Meteo 历史 ECMWF IFS HRES 单次预报进行逐站、逐日、1–3 天提前量验证。报告输出混淆矩阵、晴/晴间多云识别 precision/recall/F1，以及云量 MAE 和偏差。该数据是机场/地面站云况代理，不是日照时数传感器；样本不足时不得据此调整生产阈值或宣传预测准确率。详细口径见 docs/FORECAST_BACKTEST.md。
