import { ArrowUpRight, Cloud, CloudSun, Compass, Database, MapPinned, RadioTower, Sun, Waves } from "lucide-react";

const cities = ["成都", "重庆", "绵阳", "德阳", "遂宁", "南充", "广安", "资阳", "眉山", "乐山", "内江", "自贡", "宜宾", "泸州"];
const stages = [{time:"现在",label:"当前观测"},{time:"+24h",label:"未来一天"},{time:"+48h",label:"未来两天"},{time:"+72h",label:"未来三天"}];

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/"><span className="brand-mark"><Sun size={21}/></span><span><b>追晴</b><small>SUNSHINE FORECAST</small></span></a>
        <nav><a className="active" href="#forecast">日照预测</a><a href="#cities">城市观察</a><a href="#method">数据与方法</a></nav>
        <span className="status"><i/> MVP 数据接入准备中</span>
      </header>

      <section className="hero" id="forecast">
        <div>
          <div className="eyebrow">SICHUAN BASIN · SUNSHINE OUTLOOK</div>
          <h1>下一次太阳，<br/><em>什么时候来？</em></h1>
          <p>追踪云层、日照与天气模型变化，寻找四川盆地下一次真正放晴的时间窗口。</p>
          <div className="hero-meta"><span><MapPinned size={15}/> 四川盆地 · 14 个重点城市</span><span><RadioTower size={15}/> 数据源尚未初始化</span></div>
        </div>
        <div className="sun-art" aria-hidden="true"><div className="orbit orbit-a"/><div className="orbit orbit-b"/><div className="sun-disc"><Sun size={52}/></div><div className="cloud cloud-a"/><div className="cloud cloud-b"/><small>SUNLIGHT WINDOW</small></div>
      </section>

      <section className="metrics">
        <article className="metric featured"><label><Sun size={15}/> 下一次放晴</label><strong className="pending">等待数据接入</strong><small>待气象模型数据完成采集后生成</small></article>
        <article className="metric"><label><Waves size={15}/> 预计日照时长</label><strong>— <small>小时</small></strong><small>暂未生成预测结果</small></article>
        <article className="metric"><label><CloudSun size={15}/> 盆地日照覆盖</label><strong>— <small>%</small></strong><small>等待网格数据计算</small></article>
        <article className="metric"><label><Compass size={15}/> 模型一致性</label><strong className="pending">待评估</strong><small>IFS / AIFS 数据尚未接入</small></article>
      </section>

      <section className="panel map-panel">
        <div className="section-head"><div><label>REGIONAL SUNSHINE MAP</label><h2>四川盆地日照分布</h2><p>按时间查看各区域日照窗口变化</p></div><div className="legend"><span><i className="sun-dot"/>有效日照</span><span><i className="cloud-dot"/>云层覆盖</span><span><i className="wait-dot"/>数据待接入</span></div></div>
        <div className="map-stage"><div className="map-grid"/><div className="map-watermark">SICHUAN BASIN</div><div className="map-empty"><MapPinned size={25}/><b>日照网格正在准备中</b><span>完成盆地边界与气象数据接入后，这里将显示逐网格日照预测。</span></div><small className="map-note">MAP LAYER · NOT YET AVAILABLE</small></div>
        <div className="timeline">{stages.map(s=><div key={s.time}><i/><b>{s.time}</b><small>{s.label}</small><em>等待预测</em></div>)}</div>
      </section>

      <section className="lower">
        <article className="panel trend"><div className="section-head"><div><label>NEXT 7 DAYS</label><h2>未来 7 天日照趋势</h2></div><span className="muted-tag">等待模型数据</span></div><div className="chart-empty"><div className="chart-lines"><i/><i/><i/><i/></div><div><Cloud size={23}/><span>数据接入后生成逐日日照趋势</span></div><footer>{["周一","周二","周三","周四","周五","周六","周日"].map(x=><span key={x}>{x}</span>)}</footer></div></article>
        <article className="panel city-panel" id="cities"><div className="section-head"><div><label>CITY WATCH</label><h2>城市日照观察</h2></div><span className="muted-tag">14 CITIES</span></div><div className="city-list">{cities.map((city,i)=><div key={city}><small>{String(i+1).padStart(2,"0")}</small><b>{city}</b><span>等待预测</span><ArrowUpRight size={13}/></div>)}</div></article>
      </section>

      <section className="method" id="method"><span><Database size={19}/></span><div><b>让每一次预测都有据可查</b><p>追晴将记录模型来源、预报批次、有效时间与历史误差，不用未经验证的概率制造确定性。</p></div><small>ENGINE INITIALIZING</small></section>
      <footer className="footer"><span>追晴 SUNSHINE FORECAST</span><span>四川盆地日照预测 · 数据接入准备阶段</span></footer>
    </main>
  );
}
