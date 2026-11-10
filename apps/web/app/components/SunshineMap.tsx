"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { FeatureCollection, Geometry } from "geojson";
import { dataUrl } from "../lib/static-data";
import "maplibre-gl/dist/maplibre-gl.css";

type GeometryProps = { location_key: string; area_km2: number };
type GridGeometry = FeatureCollection<Geometry, GeometryProps>;
type GridSnapshot = {
  valid_at: string;
  // Index is aligned with geography/grid.geojson; geometry is never duplicated.
  values: Array<[number | null, number | null, number | null, number]>;
};
type Props = { gridFile: string | null };

const emptyGeoJSON: FeatureCollection = { type: "FeatureCollection", features: [] };

export default function SunshineMap({ gridFile }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [geometry, setGeometry] = useState<GridGeometry | null>(null);
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
              0, "#dce7e9", 15, "#e5d98d", 30, "#edb44d",
              45, "#dc842d", 60, "#ca682b",
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
        const minuteText = props.sunshine_minutes === null || props.sunshine_minutes === undefined
          ? "暂无预报" : Number(props.sunshine_minutes).toFixed(0) + " 分钟有效日照";
        new maplibregl.Popup({ closeButton: false, offset: 8 })
          .setLngLat(event.lngLat)
          .setHTML(
            "<div style='font:12px sans-serif;color:#294658'><b>" +
            minuteText + "</b><br/><span style='color:#87979e'>网格面积 " +
            Number(props.area_km2 ?? 0).toFixed(1) + " km²</span></div>",
          )
          .addTo(map);
      });
      map.on("mouseenter", "sunshine-fill", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "sunshine-fill", () => {
        map.getCanvas().style.cursor = "";
      });
      setMapReady(true);
    });
    map.on("error", () => setMapError(true));
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(dataUrl("geography/grid.geojson"), {
      cache: "no-store", signal: controller.signal,
    })
      .then(response => {
        if (!response.ok) throw new Error("Geography file not available");
        return response.json() as Promise<GridGeometry>;
      })
      .then(data => {
        if (data.type !== "FeatureCollection") {
          throw new Error("Unexpected GeoJSON geography");
        }
        setGeometry(data);
      })
      .catch(error => {
        if (error instanceof Error && error.name !== "AbortError") setMapError(true);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const source = mapRef.current.getSource("sunshine-cells") as maplibregl.GeoJSONSource;
    if (!gridFile || !geometry?.features.length) {
      source?.setData(emptyGeoJSON);
      return;
    }

    const controller = new AbortController();
    fetch(dataUrl(gridFile), { cache: "no-store", signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error("Missing grid forecast snapshot");
        return response.json() as Promise<GridSnapshot>;
      })
      .then(snapshot => {
        if (!Array.isArray(snapshot.values) ||
            snapshot.values.length !== geometry.features.length) {
          throw new Error("Grid snapshot count does not match geography");
        }
        const features = geometry.features.map((feature, index) => {
          const values = snapshot.values[index];
          return {
            ...feature,
            properties: {
              ...feature.properties,
              sunshine_minutes: values[0],
              cloud_cover_pct: values[1],
              precipitation_mm: values[2],
              is_interpolated: Boolean(values[3]),
            },
          };
        });
        const layer = mapRef.current?.getSource("sunshine-cells") as
          | maplibregl.GeoJSONSource | undefined;
        layer?.setData({ type: "FeatureCollection", features });
        setMapError(false);
      })
      .catch(error => {
        if (error instanceof Error && error.name !== "AbortError") {
          source?.setData(emptyGeoJSON);
          setMapError(true);
        }
      });
    return () => controller.abort();
  }, [gridFile, geometry, mapReady]);

  return (
    <>
      <div ref={containerRef} className="sunshine-map"
        aria-label="四川盆地逐网格日照预测地图"/>
      {mapError && <div className="map-overlay">
        <span aria-hidden="true" style={{ fontSize: 22 }}>⌖</span>
        <b>地图数据暂时无法加载</b>
        <span>检查网络或最近一次 GitHub Pages 数据更新记录。</span>
      </div>}
    </>
  );
}
