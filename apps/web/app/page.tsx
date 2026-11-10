"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight, Cloud, CloudSun, Compass, Database, MapPinned,
  RadioTower, Sun, Waves
} from "lucide-react";
import SunshineMap from "./components/SunshineMap";
import { dataUrl } from "./lib/static-data";

const MODELS = [
  { id: "ecmwf_ifs", name: "ECMWF IFS HRES · 9 km" },
  { id: "ecmwf_ifs025", name: "ECMWF IFS · 0.25°" },
  { id: "ecmwf_aifs025_single", name: "ECMWF AIFS · 0.25°" },
];

type SunshineWindow = {
  starts_at: string;
  ends_at: string;
  expected_sunshine_minutes: number;
  coverage_pct?: number;
  source_model?: string;
  basis?: string;
};

type Hour = {
  valid_at: string;
  sunshine_minutes: number | null;
  sunshine_coverage_pct: number | null;
  data_completeness_pct: number;
  cloud_cover_pct: number | null;
  precipitation_mm: number | null;
  interpolated_area_pct: number | null;
  grid_file?: string;
};

type Overview = {
  status: string;
  generated_at: string;
  next_sunshine_window: SunshineWindow | null;
  hourly: Hour[];
  daily_sunshine_hours: { date: string; sunshine_hours: number | null; mean_sunshine_coverage_pct: number | null; status: string }[];
  coverage: number | null;
  message: string;
  model: { model_name: string; model_run_at: string; retrieved_at: string; spatial_resolution_km: number } | null;
};

type City = {
  slug: string;
  name: string;
  next_sunshine_window: SunshineWindow | null;
  daily: { date: string; sunshine_hours: number | null; status: string }[];
  status: string;
};

type ConsensusDay = {
  date: string;
  condition: string;
  condition_label: string;
  model_count: number;
  agreement_count: number;
  agreement_pct: number;
  agreement_label: string;
  sunshine_hours: number | null;
  sunny_score: number | null;
};
type Consensus = {
  status: string;
  model_count: number;
  daily: ConsensusDay[];
  best_sunny_day: ConsensusDay | null;
  method: { version: string; note: string };
};
type DataStatus = {
  status: string;
  message: string;
  models: { model_id: string; model_name: string; status: string; model_run_at: string | null; retrieved_at: string | null; locations_count: number }[];
};

function formatTime(value?: string | null, withDate = true) {
  if (!value) return "等待数据";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间待确认";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    ...(withDate ? { month: "numeric", day: "numeric" } : {}),
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date);
}

function hourLabel(value: string) {
  const end = new Date(value);
  const start = new Date(end.getTime() - 60 * 60 * 1000);
  const formatHour = (date: Date) => new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", hour: "2-digit", hour12: false,
  }).format(date);
  return formatHour(start) + "–" + formatHour(end) + "时";
}

export default function Home() {
  const [model, setModel] = useState("ecmwf_ifs");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [cities, setCities] = useState<City[]>([]);
  const [dataStatus, setDataStatus] = useState<DataStatus | null>(null);
  const [consensus, setConsensus] = useState<Consensus | null>(null);
  const [selectedTime, setSelectedTime] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      fetch(dataUrl("overview/" + model + ".json"), { cache: "no-store", signal: controller.signal }).then(r => {
        if (!r.ok) throw new Error("日照预测静态快照尚未生成");
        return r.json() as Promise<Overview>;
      }),
      fetch(dataUrl("cities/" + model + ".json"), { cache: "no-store", signal: controller.signal }).then(r => {
        if (!r.ok) throw new Error("城市预测静态快照尚未生成");
        return r.json() as Promise<{ cities: City[] }>;
      }),
      fetch(dataUrl("status.json"), { cache: "no-store", signal: controller.signal }).then(r => {
        if (!r.ok) throw new Error("数据状态静态快照尚未生成");
        return r.json() as Promise<DataStatus>;
      }),
      fetch(dataUrl("consensus.json"), { cache: "no-store", signal: controller.signal }).then(r => {
        if (!r.ok) throw new Error("多模型综合判断尚未生成");
        return r.json() as Promise<Consensus>;
      }),
    ]).then(([nextOverview, cityData, nextStatus, nextConsensus]) => {
      setOverview(nextOverview);
      setCities(cityData.cities || []);
      setDataStatus(nextStatus);
      setConsensus(nextConsensus);
      setSelectedTime(nextOverview.hourly?.[0]?.valid_at || "");
    }).catch(err => {
      if (err instanceof Error && err.name !== "AbortError") setError(err.message || "暂时无法连接追晴服务");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [model]);

  const selectedHour = useMemo(
    () => overview?.hourly.find(item => item.valid_at === selectedTime) || overview?.hourly[0],
    [overview, selectedTime],
  );
  const maxDaily = Math.max(1, ...((overview?.daily_sunshine_hours || []).map(day => day.sunshine_hours || 0)));
  const activeModel = dataStatus?.models.find(item => item.model_id === model);
  const retrievalTime = activeModel?.retrieved_at ? Date.parse(activeModel.retrieved_at) : NaN;
  const isStale = Number.isFinite(retrievalTime) && Date.now() - retrievalTime > 12 * 3600 * 1000;
  const liveStatus = isStale ? "degraded" : dataStatus?.status;


  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/"><span className="brand-mark"><Sun size={21}/></span><span><b>追晴</b><small>SUNSHINE FORECAST</small></span></a>
        <nav><a className="active" href="#forecast">日照预测</a><a href="#cities">城市观察</a><a href="#method">数据与方法</a></nav>
        <span className={"status " + (liveStatus === "available" ? "online" : liveStatus === "degraded" ? "degraded" : "offline")}><i/> {isStale ? "预报更新延迟" : liveStatus === "available" ? "模型数据已接入" : liveStatus === "degraded" ? "部分数据可用" : "等待真实数据"}</span>
      </header>

      <section className="hero" id="forecast">
        <div className="hero-copy">
          <div className="eyebrow">SICHUAN BASIN · SUNSHINE OUTLOOK</div>
          <h1>下一次太阳，<br/><em>什么时候来？</em></h1>
          <p>追踪四川盆地云层与日照变化，从多个数值天气预报模型中寻找更值得期待的放晴时间窗口。</p>
          <div className="hero-meta">
            <span><MapPinned size={15}/> 四川盆地 · 14 个重点城市</span>
            <span><RadioTower size={15}/> {overview?.model ? "最近预报 " + formatTime(overview.model.model_run_at) : "等待模型批次"}</span>
          </div>
        </div>
        <div className="sun-art" aria-hidden="true"><div className="orbit orbit-a"/><div className="orbit orbit-b"/><div className="sun-disc"><Sun size={52}/></div><div className="cloud cloud-a"/><div className="cloud cloud-b"/><small>SUNLIGHT WINDOW</small></div>
      </section>

      {error && <div className="error-note">{error}。请查看 GitHub Actions 最近一次数据更新任务。</div>}
      {loading && <div className="loading-line"/>}
      {isStale && <div className="warning-note">天气快照超过 12 小时未更新，当前结果可能过期，请以模型初始化时间和天气实况为准。</div>}

      <section className="metrics">
        <article className="metric featured"><label><Sun size={15}/> 多模型晴好候选日</label><strong className="value pending">{consensus?.best_sunny_day ? new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",month:"numeric",day:"numeric"}).format(new Date(consensus.best_sunny_day.date + "T12:00:00+08:00")) + " · " + consensus.best_sunny_day.condition_label : "暂未发现一致候选日"}</strong><small className="metric-note">{consensus?.best_sunny_day ? consensus.best_sunny_day.agreement_label + "；不是晴天概率" : "需要至少两个可用模型给出晴好方向"}</small></article>
        <article className="metric"><label><Waves size={15}/> 所选时次平均日照</label><strong>{selectedHour?.sunshine_minutes == null ? "—" : selectedHour.sunshine_minutes.toFixed(0)} <small>分钟/小时</small></strong><small className="metric-note">按网格有效面积加权</small></article>
        <article className="metric"><label><CloudSun size={15}/> 有效日照覆盖</label><strong>{selectedHour?.sunshine_coverage_pct == null ? "—" : selectedHour.sunshine_coverage_pct.toFixed(0)} <small>%</small></strong><small className="metric-note">每小时有效日照不少于 30 分钟的区域占比</small></article>
        <article className="metric"><label><Compass size={15}/> 数据完整度</label><strong>{selectedHour?.data_completeness_pct == null ? "—" : selectedHour.data_completeness_pct.toFixed(0)} <small>%</small></strong><small className="metric-note">本时次有有效日照数据的网格面积</small></article>
      </section>

      <section className="panel consensus-panel">
        <div className="section-head">
          <div><label>MULTI-MODEL OUTLOOK · V1.1</label><h2>未来 7 天晴好判断</h2><p>综合总云量、低云量、有效日照和降水，避免仅凭日照时长误判放晴</p></div>
          <span className="muted-tag">{consensus?.model_count || 0}/3 MODELS</span>
        </div>
        <div className="consensus-days">
          {(consensus?.daily || []).map(day => <article key={day.date} className={"consensus-day " + (consensus?.best_sunny_day?.date === day.date ? "best" : "")}>
            <small>{new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",month:"numeric",day:"numeric"}).format(new Date(day.date + "T12:00:00+08:00"))}</small>
            <b>{day.condition_label}</b>
            <span>{day.sunshine_hours == null ? "日照 —" : "日照 " + day.sunshine_hours.toFixed(1) + "h"}</span>
            <em>{day.agreement_label}</em>
          </article>)}
          {!consensus?.daily?.length && <div className="chart-empty">等待至少两个模型的有效日照与云层诊断数据</div>}
        </div>
        <p className="consensus-note">{consensus?.method?.note || "模型一致性仅作方向参考；尚未使用地面观测进行准确率校准。"}</p>
      </section>

      <section className="panel map-panel">
        <div className="section-head">
          <div><label>REGIONAL SUNSHINE MAP</label><h2>四川盆地日照分布</h2><p>按网格面积查看各区域每小时预计有效日照</p></div>
          <div className="map-toolbar">
            <label htmlFor="model-select">预报模型</label>
            <select id="model-select" className="model-select" value={model} onChange={e => setModel(e.target.value)}>
              {MODELS.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}
            </select>
          </div>
        </div>
        <div className="map-stage">
          <SunshineMap gridFile={selectedHour?.grid_file ?? null}/>
          {(!overview?.hourly?.length || !overview.model) && <div className="map-overlay"><MapPinned size={25}/><b>{loading ? "正在读取日照网格" : "日照网格尚未接入"}</b><span>{overview?.message || "完成地理数据导入和模型预报采集后，这里将展示四川盆地逐网格日照分布。"}</span></div>}
        </div>
        <div className="row" style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,marginTop:12,flexWrap:"wrap"}}>
          <div className="map-key"><i className="k1"/><span>少于 15 分钟</span><i className="k2"/><span>15–30 分钟</span><i className="k3"/><span>30–45 分钟</span><i className="k4"/><span>45–60 分钟</span></div>
          <div className="data-source"><span className="dot"/> Open-Meteo · {overview?.model?.model_name || "等待模型批次"}</div>
        </div>
        <div className="hour-strip">
          {(overview?.hourly || []).slice(0, 72).map(hour => (
            <button type="button" key={hour.valid_at} className={"hour-chip " + (selectedHour?.valid_at === hour.valid_at ? "selected" : "")} onClick={() => setSelectedTime(hour.valid_at)}>
              <b>{hourLabel(hour.valid_at)}</b>
              <span>日照覆盖</span>
              <em>{hour.sunshine_coverage_pct == null ? "—" : hour.sunshine_coverage_pct.toFixed(0) + "%"}</em>
            </button>
          ))}
          {!overview?.hourly?.length && <span className="muted-tag">暂无可选时次</span>}
        </div>
        <p className="map-footnote">地图颜色表示每个网格在所选小时内的预计有效日照分钟数。网格按 USGS 概化盆地边界裁剪，非行政区划边界；底图 © OpenStreetMap contributors。</p>
      </section>

      <section className="lower">
        <article className="panel trend">
          <div className="section-head"><div><label>NEXT 7 DAYS</label><h2>未来 7 天日照趋势</h2></div><span className="muted-tag">{overview?.model ? "模型预报 · 面积加权" : "等待模型数据"}</span></div>
          {overview?.daily_sunshine_hours?.length ? (
            <>
              <div className="daily-bars">
                {overview.daily_sunshine_hours.map(day => (
                  <div className="day-col" key={day.date}>
                    <strong>{day.sunshine_hours == null ? "—" : day.sunshine_hours.toFixed(1) + "h"}</strong>
                    <div className="day-bar-wrap"><div className="day-bar" style={{height:Math.max(2,((day.sunshine_hours || 0)/maxDaily)*100) + "%"}}/></div>
                    <small>{new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",month:"numeric",day:"numeric"}).format(new Date(day.date + "T12:00:00+08:00"))}</small>
                  </div>
                ))}
              </div>
              <p className="daily-caption">日照时长为盆地网格面积加权平均值，单位：小时/日。</p>
            </>
          ) : <div className="chart-empty"><div className="chart-lines"><i/><i/><i/><i/></div><div><Cloud size={23}/><span>接入模型数据后生成逐日日照趋势</span></div></div>}
        </article>

        <article className="panel city-panel" id="cities">
          <div className="section-head"><div><label>CITY WATCH</label><h2>城市日照观察</h2></div><span className="muted-tag">{cities.length || 14} CITIES</span></div>
          {cities.length ? <div className="city-list">
            {cities.map((city,index)=><Link href={"/city/" + city.slug + "?model=" + model} key={city.slug}>
              <small>{String(index+1).padStart(2,"0")}</small><b>{city.name}</b>
              <span>{city.next_sunshine_window ? formatTime(city.next_sunshine_window.starts_at,false) : "暂无连续日照"}</span><ArrowUpRight size={13}/>
            </Link>)}
          </div> : <div className="warning-note">城市点位和预报数据导入后，将显示成都、重庆及盆地周边重点城市的日照窗口。</div>}
        </article>
      </section>

      <section className="method" id="method"><span><Database size={19}/></span><div><b>让每一次预测都有据可查</b><p>{overview?.model ? "当前展示 " + overview.model.model_name + "，初始化时间 " + formatTime(overview.model.model_run_at) + "，采集时间 " + formatTime(overview.model.retrieved_at) + "。" : "追晴将记录模型来源、预报批次、有效时间与历史误差，不用未经验证的概率制造确定性。"}</p></div><small>{dataStatus?.status === "available" ? "DATA CONNECTED" : "DATA INITIALIZING"}</small></section>
      <div className="warning-note">V1.1 判定口径：晴天分类联合使用晴空覆盖（总云量≤30%、低云量≤25%）、明亮覆盖（总云量≤65%、低云量≤50%）、有效日照与降水条件；放晴窗口至少连续 3 小时，并要求云层诊断完整度≥80%、插值网格面积不超过50%。多模型采用等权分类投票，不将相关模型包装成概率。所有阈值均为透明的产品规则，尚未通过地面观测校准。</div>
      <footer className="footer">
        <span>追晴 SUNSHINE FORECAST</span>
        <span className="footer-attribution">
          气象数据 <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo.com</a> ·
          城市数据 <a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames</a>（CC BY 4.0）·
          盆地边界 <a href="https://pubs.usgs.gov/of/2000/of00-047/" target="_blank" rel="noreferrer">USGS OFR 00-047</a>
        </span>
        <span>日照指标由追晴基于模型预报计算，尚未完成地面站点校准</span>
      </footer>
    </main>
  );
}
