"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { FeatureCollection, Geometry } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";

type MapData = {
  status: string;
  valid_at: string | null;
  geojson: FeatureCollection<Geometry, {
    sunshine_minutes: number | null;
    cloud_cover_pct: number | null;
    precipitation_mm: number | null;
    area_km2: number | null;
    location_key: string;
  }>;
};

type Props = { apiBase: string; model: string; validAt: string };

const emptyGeoJSON: FeatureCollection = { type: "FeatureCollection", features: [] };

export default function SunshineMap({ apiBase, model, validAt }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [105.45, 30.55],
      zoom: 6.1,
      minZoom: 5,
      maxZoom: 10,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("sunshine-cells", { type: "geojson", data: emptyGeoJSON });
      map.addLayer({
        id: "sunshine-fill",
        type: "fill",
        source: "sunshine-cells",
        paint: {
          "fill-color": [
            "case",
            ["==", ["get", "sunshine_minutes"], null], "#cbd9dc",
            ["interpolate", ["linear"], ["get", "sunshine_minutes"],
              0, "#dce7e9", 15, "#e5d98d", 30, "#edb44d", 45, "#dc842d", 60, "#ca682b"
            ],
          ],
          "fill-opacity": 0.76,
          "fill-outline-color": "#ffffff",
        },
      });
      map.addLayer({
        id: "sunshine-outline",
        type: "line",
        source: "sunshine-cells",
        paint: { "line-color": "#ffffff", "line-width": 0.6, "line-opacity": 0.7 },
      });
      map.on("click", "sunshine-fill", event => {
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties || {};
        const minutes = props.sunshine_minutes;
        const area = props.area_km2;
        new maplibregl.Popup({ closeButton: false, offset: 8 })
          .setLngLat(event.lngLat)
          .setHTML("<div style='font:12px sans-serif;color:#294658'><b>" + Number(minutes ?? 0).toFixed(0) + " 分钟有效日照</b><br/><span style='color:#87979e'>网格面积 " + Number(area ?? 0).toFixed(1) + " km²</span></div>")
          .addTo(map);
      });
      map.on("mouseenter", "sunshine-fill", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "sunshine-fill", () => { map.getCanvas().style.cursor = ""; });
      setMapReady(true);
    });
    map.on("error", () => setMapError(true));
    return () => {
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ model });
    if (validAt) params.set("valid_at", validAt);
    fetch(apiBase + "/api/v1/grid?" + params.toString(), { cache: "no-store", signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error("map data unavailable");
        return response.json() as Promise<MapData>;
      })
      .then(data => {
        const source = mapRef.current?.getSource("sunshine-cells") as maplibregl.GeoJSONSource | undefined;
        source?.setData(data.geojson || emptyGeoJSON);
      })
      .catch(error => {
        if (error instanceof Error && error.name !== "AbortError") setMapError(true);
      });
    return () => controller.abort();
  }, [apiBase, model, validAt, mapReady]);

  return (
    <>
      <div ref={containerRef} className="sunshine-map" aria-label="四川盆地逐网格日照预测地图"/>
      {mapError && <div className="map-overlay"><MapFallbackIcon/><b>地图底图暂时无法加载</b><span>请检查网络连接。预测数据接口仍可独立查看。</span></div>}
    </>
  );
}

function MapFallbackIcon() {
  return <span aria-hidden="true" style={{ fontSize: 22 }}>⌖</span>;
}
