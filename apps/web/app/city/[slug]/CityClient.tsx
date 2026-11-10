"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Sun, MapPin } from "lucide-react";
import { useParams } from "next/navigation";
import { dataUrl } from "../../lib/static-data";


type CityData = {
  name: string;
  latitude: number;
  longitude: number;
  next_sunshine_window: { starts_at: string; ends_at: string; expected_sunshine_minutes: number; basis: string } | null;
  daily: { date: string; sunshine_hours: number | null; status: string }[];
  hourly: { valid_at: string; sunshine_minutes: number | null; cloud_cover_pct: number | null; precipitation_mm: number | null; temperature_c: number | null; is_interpolated: boolean }[];
};

function fmt(value: string) {
  return new Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(value));
}

function fmtHourRange(value: string) {
  const end = new Date(value);
  const start = new Date(end.getTime() - 60 * 60 * 1000);
  const date = new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai",month:"numeric",day:"numeric"}).format(start);
  const hour = (value: Date) => new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai",hour:"2-digit",hour12:false}).format(value);
  return date + " " + hour(start) + "–" + hour(end) + "时";
}

export default function CityPage() {
  const params = useParams<{slug:string}>();
  const [city,setCity] = useState<CityData|null>(null);
  const [selectedModel,setSelectedModel] = useState("ecmwf_ifs");
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("model");
    if (requested && ["ecmwf_ifs","ecmwf_ifs025","ecmwf_aifs025_single"].includes(requested)) {
      setSelectedModel(requested);
    }
  }, []);
  const [model,setModel] = useState<{model_name:string;model_run_at:string;retrieved_at:string}|null>(null);
  const [error,setError] = useState("");
  const [loading,setLoading] = useState(true);

  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);
    setError("");
    fetch(dataUrl("city/" + selectedModel + "/" + params.slug + ".json"),{cache:"no-store",signal:controller.signal})
      .then(r=>{if(!r.ok) throw new Error("当前没有该城市的可用预报数据"); return r.json();})
      .then(data=>{setCity(data.city);setModel(data.model);})
      .catch(err=>{if(err instanceof Error&&err.name!=="AbortError")setError(err.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[params.slug,selectedModel]);

  return <main className="shell city-page">
    <Link href="/" className="back-link"><ArrowLeft size={14}/> 返回四川盆地总览</Link>
    {loading&&<div className="loading-line"/>}
    {error&&<div className="error-note">{error}。请查看 GitHub Actions 的预报采集任务。</div>}
    {city&&<>
      <section className="city-hero">
        <label style={{fontSize:10,color:"#84959e",display:"block",marginBottom:12}} htmlFor="city-model">预报模型</label>
        <select id="city-model" className="model-select" value={selectedModel} onChange={event=>setSelectedModel(event.target.value)}>
          <option value="ecmwf_ifs">ECMWF IFS HRES</option>
          <option value="ecmwf_ifs025">ECMWF IFS 0.25°</option>
          <option value="ecmwf_aifs025_single">ECMWF AIFS 0.25°</option>
        </select>
        <div className="eyebrow">CITY SUNSHINE OUTLOOK</div>
        <h1>{city.name} · 日照预测</h1>
        <p><MapPin size={13} style={{display:"inline",verticalAlign:"middle"}}/> {city.latitude.toFixed(3)}°N, {city.longitude.toFixed(3)}°E　·　{model?.model_name}</p>
        <div className="window-card">
          <label><Sun size={13} style={{display:"inline",verticalAlign:"middle"}}/> 下一次连续日照窗口</label>
          <strong>{city.next_sunshine_window?fmt(city.next_sunshine_window.starts_at) + " — " + fmt(city.next_sunshine_window.ends_at):"当前预报周期内暂未发现"}</strong>
          <small>{city.next_sunshine_window ? "窗口内累计预计有效日照 " + (city.next_sunshine_window.expected_sunshine_minutes / 60).toFixed(1) + " 小时。" : "每小时预计有效日照不少于 30 分钟，连续至少 2 小时。"} {city.next_sunshine_window?.basis || ""}</small>
        </div>
      </section>
      <section className="city-stats">
        <article><label>未来 7 天日照总量</label><strong>{city.daily.reduce((sum,d)=>sum+(d.sunshine_hours||0),0).toFixed(1)} 小时</strong></article>
        <article><label>预报时次数</label><strong>{city.hourly.length} 个</strong></article>
        <article><label>数据更新时间</label><strong style={{fontSize:14}}>{model?.retrieved_at?fmt(model.retrieved_at):"—"}</strong></article>
      </section>
      <section className="panel">
        <div className="section-head"><div><label>HOURLY FORECAST</label><h2>逐小时日照与天气</h2></div><span className="muted-tag">LOCAL TIME · UTC+8</span></div>
        <div className="city-hourly">
          {city.hourly.slice(0,48).map(hour=><div className="city-hour" key={hour.valid_at}>
            <b>{fmtHourRange(hour.valid_at)}</b>
            <strong>{hour.sunshine_minutes==null?"—":hour.sunshine_minutes.toFixed(0) + " min"}</strong>
            <small>{hour.cloud_cover_pct==null?"云量 —":"云量 " + hour.cloud_cover_pct.toFixed(0) + "%"}　{hour.temperature_c==null?"":hour.temperature_c.toFixed(0) + "℃"}</small>
          </div>)}
        </div>
      </section>
      {model?.retrieved_at && Date.now() - Date.parse(model.retrieved_at) > 12 * 3600 * 1000 && <p className="warning-note">该城市的模型快照已超过 12 小时未更新，请谨慎参考。</p>}
      <p className="warning-note">日照时长来自 Open-Meteo 模型预报字段，非地面实测。小时级预报可能包含模型时间分辨率插值，请结合预报批次与实际天气判断。</p>
    </>}
    <footer className="footer">
        <span>追晴 SUNSHINE FORECAST</span>
        <span className="footer-attribution">
          气象数据 <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo.com</a> ·
          城市数据 <a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames</a>（CC BY 4.0）·
          盆地边界 <a href="https://pubs.usgs.gov/of/2000/of00-047/" target="_blank" rel="noreferrer">USGS OFR 00-047</a>
        </span>
        <span>日照指标由追晴基于模型预报计算，尚未完成地面站点校准</span>
      </footer>
  </main>;
}
