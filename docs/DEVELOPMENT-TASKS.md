# 静态 MVP 验收清单

## 已实现
- [x] 从原全栈版本创建 feature/github-pages-static-mvp 独立分支。
- [x] 复用 USGS/GeoNames 数据导入算法，不依赖 PostGIS。
- [x] 复用 ECMWF 单轮预报采集、时次和插值标记。
- [x] 地图几何独立存储，逐时网格仅保存紧凑数值数组。
- [x] 无真实数据时显示 initializing，不能生成假预测。
- [x] Next.js output=export，14个城市路由静态生成。
- [x] 前端改为读取同源静态 JSON，而非 FastAPI。
- [x] GitHub Actions 每4小时触发生成并自动发布的工作流。
- [x] CI 通过 Python 测试、TypeScript、ESLint 与 14 城页面静态构建。

## 尚待线上验收
- [ ] 在 GitHub Actions 实际下载天气模型，并检查数据完整度和有效时间。
- [ ] 合并至 main 并启用 GitHub Pages Actions 发布源。
- [ ] 检查真实 github.io 公网地址、地图图层与14城访问。
- [ ] 观察更新延迟、API 速率限制和中国大陆网络连通性。
- [ ] 后续对接地面气象站实况开展误差回测。

## 安全边界
- 非商业 API/Pages 使用规则须在公开使用前复核。
- 由于没有校准观测数据，产品不能展示经过测量的准确率或晴天概率。
