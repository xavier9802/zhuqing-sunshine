export type ServiceStatus = "initializing" | "available" | "degraded";

export interface DataStatus {
  status: ServiceStatus;
  provider: string;
  latest_model_run: string | null;
  last_checked_at: string;
  message: string;
}

export interface SunshineWindow {
  starts_at: string;
  ends_at: string;
  expected_sunshine_minutes: number;
  source_model: string;
}

export interface DailySunshineSummary {
  date: string;
  sunshine_minutes: number | null;
  status: "pending" | "low" | "moderate" | "high";
}

export interface BasinOverview {
  status: ServiceStatus;
  region: "sichuan-basin";
  timezone: "Asia/Shanghai";
  generated_at: string;
  next_sunshine_window: SunshineWindow | null;
  daily_sunshine_hours: DailySunshineSummary[];
  coverage: number | null;
  message: string;
}
