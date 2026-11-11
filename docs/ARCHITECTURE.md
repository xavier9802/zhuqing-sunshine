# 追晴 Lite：Static-First 架构

## 数据流

1. GitHub Actions 每四小时尝试触发 Python 快照生成器。
2. 下载/读取缓存的 USGS 盆地代理边界与 GeoNames 14 城市点位；生成 0.25° 裁剪网格与面积权重。
3. 逐模型读取 Open-Meteo 发布元数据，使用模型初始化时次精确请求 Single Runs API。
4. 对网格与城市按位置批量采集 sunshine_duration、cloud_cover、precipitation、temperature_2m。每个模型单独处理失败。
5. Python 计算盆地面积加权日照、连续窗口与各城市逐时/逐日结果。
6. 写入 apps/web/public/data 的静态 JSON，构建 Next.js export，上传 GitHub Pages artifact。
7. 访问者只请求 github.io 站点内的 HTML、JavaScript、JSON 和 GeoJSON，不直接查询气象商接口。

## 静态数据契约

所有文件均生成于构建时，不提交大量天气预报快照到 Git 仓库。

- data/status.json — 所有模型的采集状态、初始化/检索时次。
- data/overview/{model_id}.json — 72 小时盆地汇总、窗口和 7 天趋势；hourly[].grid_file 指向数值切片。
- data/cities/{model_id}.json — 14 城市列表和日照窗口。
- data/city/{model_id}/{slug}.json — 城市逐小时与逐日预报。
- data/geography/grid.geojson — 单份网格几何，包含位置键与裁剪面积。
- data/geography/boundary.geojson — USGS 概化盆地边界。
- data/geography/cities.json — GeoNames 城市目录。
- data/grid/{model_id}/{yyyyMMddTHHmmZ}.json — 与网格几何按数组顺序对齐的小时值 [日照分钟, 云量%, 降水mm, 插值标记]。

显示层只能使用已成功生成的 model snapshots。未生成/缺失值一律为 null，不以0代替，也不通过曲线拟合虚构预测。

## 网格与日照计算

- 网格面积采用 EPSG:6933 等积投影测算，边缘裁剪后参与加权。
- 每个网格每小时日照时长 >= 30分钟为有效日照；覆盖率计算需校验有效数据面积。
- 整体窗口：有效日照面积覆盖率 >=50%，数据完整度 >=80%，连续至少2小时。
- 时间戳代表此前1小时的累计日照。窗口开始时间应减去1小时，不能把它当作小时起点。
- 模型原生时间步长与提供方的逐小时插值分开标记。
- 元数据包括 model_run_at、retrieved_at、forecast_end_at、source 等。

## 失败处理与新鲜度

- 模型采集可单独失败；首页会区分 available、degraded 与 initializing。
- schedule 事件在完全拿不到真实模型时拒绝部署，以保留上次成功快照；首次推送/手动执行可以发布明确标记为无数据的页面外壳。
- GitHub Actions 可能延迟；刷新策略不是实时气象服务 SLA。
- 产品应结合实际 retrieved_at 与当前时间提示数据是否过期。
- GitHub Pages 只能托管站点文件，无法直接运行 Python、Node 服务或 Postgres。

## 发布设置

1. 将静态重构代码合并至默认分支 main。
2. 仓库 Settings → Pages → Build and deployment → Source 选择 GitHub Actions。
3. main 上的 pages.yml 开始首次部署；CI 在合并前验证构建。
4. 验收 GitHub Actions 的 Pages 构建和部署任务，检查 /data/status.json。
5. 打开 https://xavier9802.github.io/zhuqing-sunshine/，检查首页、14 个城市路由、地图切片与更新时间。

GitHub Pages 站点 URL 为预期地址，完成部署前不能声称已经上线。

## 后续优化

- 独立天气数据准确率回测需要地面实况数据；不因静态架构免除模型校验。
- 可以后续把 apps/web/out 迁移到国内静态托管而不更改采集/前端逻辑。
- GitHub Actions 的免费资源和 Open-Meteo 免费 API 受使用政策与非商业授权限制。


## V1.1 晴好天气判定

- 单独使用 sunshine_duration 会高估局地/碎片云条件下的连续晴朗感受。ECMWF 官方指南已明确提示 IFS sunshine duration 在部分场景可能高估。
- 采集总云量、低/中/高云量、降水、相对湿度、露点、短波辐射、天气代码与 is_day；字段缺失不填0。
- 晴空覆盖：有效日照≥30分钟、总云量≤30%、低云≤25%、降水<0.1mm/h。
- 明亮覆盖：有效日照≥30分钟、总云量≤65%、低云≤50%、降水<0.1mm/h。
- 盆地日照窗口至少连续3小时，明亮覆盖和有效日照覆盖均≥50%，云层/降水诊断完整度≥80%，插值面积≤50%。
- 日级分类基于白昼小时的晴空/明亮覆盖时数、平均云量、低云量和降水时数。
- 三个 ECMWF 模型等权投票生成日期方向判断；至少两个模型同向才推荐候选日。模型属于同一预报体系，不将投票比例解释为概率。
- sunny_score 是透明的比较指数，不是经校准的晴天概率。只有引入地面站点/卫星观测并完成按季节、提前量、地形分区的历史回测，才能发布准确率或概率。


## V1.2 历史验证与发布边界

- sitegen/backtest.py 使用 Open-Meteo ECMWF Single Runs 历史预报、NOAA NCEI GHCNh 站点观测和 NASA POWER 日短波辐射参考，输出逐站、逐提前量的分类指标与辐射误差。
- 2026 年作为时间外留出年份；2024–2025 年仅用于估计辐射偏差。研究性订正不自动写入生产快照。
- 目前仅 3 个机场站提供足够云况观测，未达到至少 4 个独立观测站的研究门槛。SYNOP 云量字段缺失时必须保留为缺测。
- 在获取更多独立地面云况/日照观测前，不修改线上晴天阈值，不发布概率校准或盆地级准确率。


## CloudBase runtime migration (V1.2+)

When the repository has `CLOUDBASE_ENV_ID` and `CLOUDBASE_STORAGE_PUBLIC_BASE_URL` configured, the CloudBase workflow becomes the production deployment path:

1. A single Python 3.11 CloudBase timer function runs `sitegen.build.generate` for the existing three ECMWF models. The function uses the same production algorithm and data contracts as the GitHub Pages pipeline.
2. The function writes temporary build output, validates that at least one model is available, and uploads a complete immutable snapshot to the PG-mode Storage Bucket `zhuqing-data`.
3. It updates `zhuqing/latest.json` only after every snapshot object has uploaded. The manifest points to a versioned `zhuqing/snapshots/<run_id>/data` prefix.
4. The frontend first resolves the manifest and then fetches status, consensus, city, geography and hourly grid files from the same immutable prefix. When `NEXT_PUBLIC_DATA_BASE_URL` is unset, local development and GitHub Pages continue using relative `/data` paths.
5. Two complete snapshots are retained for rollback. The previous-previous snapshot is removed only after the new manifest has been published.
6. If all models fail, the function throws before changing the manifest. If only some models succeed, it publishes the existing explicit degraded status. No fake forecast data is generated.

The timer uses the seven-field CloudBase cron expression `0 17 */4 * * * *`. The function is configured for Python 3.11, 900 seconds and 3072 MB. This is intentionally one function because the most recent complete GitHub Pages forecast build finished in about four minutes; the CloudBase runtime must still be measured on its first real run.

No custom business database tables are required. PG-mode Storage uses its own bucket/object metadata and RLS policy: anonymous/authenticated users can SELECT from `zhuqing-data`, while writes are performed only by the server-side service-role key.

See [CloudBase deployment guide](CLOUDBASE_DEPLOYMENT.md) for required GitHub Variables / Secrets, Bucket policy, CORS, first-run deployment, validation and GitHub Pages rollback.
