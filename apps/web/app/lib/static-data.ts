const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
const DATA_BASE_URL = (process.env.NEXT_PUBLIC_DATA_BASE_URL || "").replace(/\/+$/, "");

export function dataUrl(relativePath: string, dataBase = ""): string {
  const clean = relativePath.replace(/^\/+/, "");
  if (clean.includes("..") || clean.includes("?") || clean.includes("#")) {
    throw new Error("Invalid static data path");
  }
  const root = dataBase || BASE_PATH + "/data/";
  return root.replace(/\/?$/, "/") + clean;
}

/**
 * Resolve one immutable CloudBase Storage snapshot before loading any data.
 * When no CloudBase base URL is configured, keep GitHub Pages/local static data
 * working as the rollback path.
 */
export async function resolveDataBase(signal?: AbortSignal): Promise<string> {
  if (!DATA_BASE_URL) {
    return BASE_PATH + "/data/";
  }

  const response = await fetch(DATA_BASE_URL + "/zhuqing/latest.json", {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error("追晴云端数据清单暂不可用，请稍后重试");
  }

  const manifest = await response.json() as { data_prefix?: unknown };
  const prefix = manifest.data_prefix;
  if (
    typeof prefix !== "string" ||
    !/^zhuqing\/snapshots\/[0-9TZ]+\/data$/.test(prefix)
  ) {
    throw new Error("追晴云端数据版本信息无效");
  }
  return DATA_BASE_URL + "/" + prefix + "/";
}
