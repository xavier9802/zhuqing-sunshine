# 追晴 CloudBase 第二阶段部署指南

## 目标架构

- 静态网站：CloudBase 静态网站托管，托管 `apps/web/out`。
- 定时计算：一个 Python 3.11 CloudBase 云函数，完整运行现有三模型采集和日照算法。
- 预测快照：PG 模式 CloudBase Storage 的公开 Bucket `zhuqing-data`。
- 调度：CloudBase Timer，每 4 小时执行一次。
- 数据库：不创建追晴业务数据表、不引入独立业务数据库。PG Storage 自身管理 Bucket 和对象元数据。

函数配置：900 秒超时、3072 MB 内存。当前 GitHub Pages 最近一次三模型完整构建约 4 分钟；CloudBase 首次运行仍需通过真实环境日志验证运行时、内存和外网访问情况。

## 一、创建 CloudBase 环境

1. 在腾讯云 CloudBase 控制台创建一个独立环境。
2. 选择 **PG 模式 / PostgreSQL 原生模式**，地域优先选择中国大陆区域。
3. 确认环境状态正常，并记录环境 ID。
4. 不需要创建业务数据库集合或额外业务表；部署流水线会创建专用 Storage Bucket。

本实现使用 PG 模式 Storage HTTP API，不兼容传统模式 Storage API。若已有传统模式环境，不要直接部署；应先新建 PG 模式环境，或单独调整存储适配器。

## 二、创建部署凭证

在 GitHub 仓库 Settings → Secrets and variables → Actions 中配置。

### Repository Variables

| 名称 | 内容 |
|---|---|
| `CLOUDBASE_ENV_ID` | CloudBase 环境 ID |
| `CLOUDBASE_STORAGE_PUBLIC_BASE_URL` | `zhuqing-data` Bucket 的公开 URL 根地址，不带末尾文件路径 |

### Repository Secrets

| 名称 | 内容 |
|---|---|
| `TENCENTCLOUD_SECRET_ID` | 用于 GitHub Actions 登录并部署 CloudBase 资源的 CAM SecretId |
| `TENCENTCLOUD_SECRET_KEY` | 对应的 CAM SecretKey |
| `CLOUDBASE_SERVICE_ROLE_KEY` | CloudBase PG 模式服务端 `service_role` API Key |

部署凭证与运行凭证分开：CAM SecretId/SecretKey 仅用于 CI 部署；service_role API Key 注入云函数运行环境，只用于写入 Storage。不要把这些凭证写入仓库、前端环境变量或公开日志。建议使用权限范围尽可能小的 CAM 子账号。

### 获取公开 URL 根地址

Bucket 创建后，在 CloudBase JS SDK 中读取公开 URL：

```ts
import cloudbase from "@cloudbase/js-sdk";

const app = cloudbase.init({ env: "你的环境 ID" });
const { data } = app.storage
  .from("zhuqing-data")
  .getPublicUrl("zhuqing/latest.json");

console.log(data.publicUrl);
```

把打印出的 URL 中末尾的 `/zhuqing/latest.json` 去掉，剩余部分填入 `CLOUDBASE_STORAGE_PUBLIC_BASE_URL`。例如最终应能访问：

```
<CLOUDBASE_STORAGE_PUBLIC_BASE_URL>/zhuqing/latest.json
```

如果使用自定义存储域名，确保该域名已绑定到这个 Bucket，且访问路径与 SDK 返回的公开 URL 一致。

## 三、Storage 权限与跨域

GitHub Actions 在部署时会执行 `cloudbase/sql/001_zhuqing_data_bucket.sql`：

- 创建或更新公开 Bucket：`zhuqing-data`。
- 单文件大小上限 10 MB。
- 给 `anon` / `authenticated` 角色授予该 Bucket 的 SELECT 读取策略。
- 不授予匿名 INSERT、UPDATE 或 DELETE 权限；云函数通过 service_role 写入。

请在 CloudBase Storage / COS 的 CORS 配置中，允许追晴静态网站的正式域名发起 GET、HEAD、OPTIONS 请求。不要为浏览器开放 service_role API Key。若同时使用 CloudBase 默认静态托管域名和自定义域名，两者都应加入允许来源。

## 四、部署和首次采集

完成上述 Variables / Secrets 后：

1. 打开 GitHub 仓库 Actions。
2. 选择 **Deploy Zhuqing to Tencent CloudBase**。
3. 点击 Run workflow。
4. 首次部署勾选 `run_initial_forecast`。
5. 等待函数部署、静态网站发布和首次三模型采集完成。

流水线会自动：
- 用 Python 3.11 为 CloudBase 函数打包现有 `sitegen` 算法与 Shapely / PyProj 等二进制依赖。
- 创建 Storage Bucket 和公开读取策略。
- 部署 `zhuqingForecastRefresh` 云函数及四小时定时触发器。
- 构建并发布静态网站。
- 如勾选首次采集，立即调用函数生成第一份真实预报快照。

## 五、快照发布协议

Bucket 内路径：

- `zhuqing/latest.json`：当前版本清单，缓存 60 秒。
- `zhuqing/snapshots/<run_id>/data/**`：版本化、不可变的 JSON / GeoJSON 快照，缓存 24 小时。
- `zhuqing/locks/<4-hour-slot>.json`：定时任务短期幂等锁。

函数先在临时目录完整运行算法，再上传该轮所有数据文件，最后才更新 `latest.json`。前端先读取清单，再按清单中的 `data_prefix` 加载同一轮数据，因此不会在发布中途切换到不完整快照。

每次成功发布后保留当前和上一份完整快照，并清理更早一轮对象。若全部模型失败，函数不会更新 `latest.json`，旧版本继续服务；若只有部分模型成功，则发布明确标记为 degraded 的快照。

## 六、运行与验收

部署后检查：

1. CloudBase 云函数列表存在 `zhuqingForecastRefresh`。
2. 函数运行时为 Python 3.11，超时 900 秒，内存 3072 MB。
3. 函数触发器显示 `0 17 */4 * * * *`，即每四小时第 17 分钟触发一次；请在控制台确认当前地域/环境的触发时区。
4. 函数日志出现三模型采集、快照上传和发布成功记录。
5. 公开访问 `<CLOUDBASE_STORAGE_PUBLIC_BASE_URL>/zhuqing/latest.json`，确认返回 `data_prefix`、模型状态和对象数量。
6. 访问 CloudBase 静态网站，检查首页、地图网格和 14 个城市详情。
7. 确认失败模拟不会覆盖上一份 `latest.json`。

## 七、GitHub Pages 回滚

设置 `CLOUDBASE_ENV_ID` 和 `CLOUDBASE_STORAGE_PUBLIC_BASE_URL` 后，GitHub Pages 的定时采集 / 发布任务会自动跳过，避免和 CloudBase 同时请求 Open-Meteo。

如需回滚：打开 **Publish sunshine forecast to GitHub Pages** 工作流，手动运行并勾选 `force_github_pages`。GitHub Pages 会重新构建并发布，CloudBase 环境和快照不会被删除。

## 八、当前边界

- Open-Meteo 当前按非商业使用配置；商业用途必须先确认许可和 API 方案。
- Python 3.11 与 CloudBase 函数的地理依赖已按二进制 wheel 打包，但仍需首次部署实测。
- 函数运行时间、内存、Open-Meteo 国内网络连通性、Storage CORS 和 CDN 缓存均以目标环境实测为准。
- 当前只有 3 个有效云况观测站，仍不发布未经充分独立验证的四川盆地整体准确率或校准概率。
