-- PG-mode CloudBase Storage bucket for public forecast snapshots.
INSERT INTO storage.buckets (
  id, name, public, file_size_limit, allowed_mime_types, created_at, updated_at
)
VALUES (
  'zhuqing-data',
  'zhuqing-data',
  TRUE,
  10485760,
  ARRAY['application/json', 'application/geo+json'],
  now(),
  now()
)
ON CONFLICT (id) DO UPDATE
SET
  public = TRUE,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types,
  updated_at = now();
