# 天气数据与地理来源（静态 MVP）

## 气象数据：Open-Meteo Single Runs API

- 数据接口：https://single-runs-api.open-meteo.com/v1/forecast
- 模型元数据：https://api.open-meteo.com/data/{model_id}/static/meta.json
- 服务文档：https://open-meteo.com/en/docs/single-runs-api

模型 ID：ecmwf_ifs（IFS HRES）、ecmwf_ifs025（IFS 0.25°）、ecmwf_aifs025_single（AIFS Single）。

站点只请求生成静态预测所需的四个小时变量：

- sunshine_duration（有效日照秒数）
- cloud_cover（总云量%）
- precipitation（降水mm）
- temperature_2m（气温℃）

所有请求发生于 GitHub Actions Python 任务中，浏览器不调用气象 API。

读取模型元数据后按 run= 指定确切初始化时间，保留来源、可用时间与检索时间。原生模型时次可能比小时稀疏；如果服务商提供插值小时值，前端必须展示相应插值状态。

Open-Meteo 免费接口属于非商业使用范围，正式商用必须先取得适用的授权。采用付费接口时须通过 Actions Secrets 提供密钥，不得提交至仓库。

## 四川盆地边界：USGS OFR 00-047

- https://pubs.usgs.gov/of/2000/of00-047/
- 源 Shapefile 为约 1:5,000,000 结构沉积盆地概化边界，并非精确地貌或行政边界。
- 公开档案缺少 .prj；元数据只声明经纬度十进制度，未明确大地基准。
- 当前按 EPSG:4326 临时解释供区域展示，保留不确定性声明。
- 0.25° 裁剪网格面积通过 EPSG:6933 等积投影测算。

## 城市点位：GeoNames

- https://download.geonames.org/export/dump/cities15000.zip
- https://download.geonames.org/export/dump/admin1CodesASCII.txt
- 授权：CC BY 4.0（需署名）
- 14城按 GeoNames 数据集及省/市代码匹配，属于城镇参考点，非行政区几何质心。

## 底图与其他

- 地图使用 OpenStreetMap 瓦片，© OpenStreetMap contributors。
- 大陆访问 github.io 和地图瓦片存在网络不确定性。
- 预测结果不是地面站实况，也未完成正式准确率标定。
