/**
 * TubeHub 前端共享类型
 *
 * 与后端 backend/app/schemas/*.py 保持一致（仅前端使用字段，不做完整镜像）。
 * 设计依据：docs/design/02-api-design.md
 */

export interface VideoRead {
  id: number;
  youtube_id: string;
  title: string;
  uploader: string | null;
  source_url: string;
  upload_date: string | null;
  duration: number | null;
  thumbnail_path: string | null;
  file_size: number | null;
  width: number | null;
  height: number | null;
  quality_label: string | null;
  last_position: number;
  last_watched_at: string | null;
  created_at: string;
}

export type DownloadStatus =
  | 'pending'
  | 'queued'
  | 'downloading'
  | 'merging'
  | 'ready'
  | 'failed'
  | 'cancelled';

export interface DownloadTaskRead {
  id: number;
  url: string;
  youtube_id: string | null;
  title: string | null;
  format_type: string;
  quality: string;
  status: DownloadStatus | string;
  progress: number;
  speed: string | null;
  eta: string | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
  created_at: string;
  finished_at: string | null;
}

export type ProxyScheme = 'http' | 'https' | 'socks5';

export interface ProxyConfigPublic {
  enabled: boolean;
  scheme: ProxyScheme;
  host: string;
  port: number;
  username: string;
}

export interface ProxyConfig extends ProxyConfigPublic {
  password: string;
}

export interface ProxyTestResponse {
  ok: boolean;
  latency_ms: number | null;
  status_code: number | null;
  error: string | null;
}

export interface CookieStatus {
  has_cookie: boolean;
  updated_at: string | null;
  file_size: number | null;
  note: string;
}