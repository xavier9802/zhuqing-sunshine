import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "追晴 · 四川盆地日照预测",
  description: "专注四川盆地日照变化，寻找下一次真正放晴的时间窗口。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
