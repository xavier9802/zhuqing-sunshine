const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export function dataUrl(relativePath: string): string {
  const clean = relativePath.replace(/^\/+/, "");
  if (clean.includes("..") || clean.includes("?")) {
    throw new Error("Invalid static data path");
  }
  return BASE_PATH + "/data/" + clean;
}
