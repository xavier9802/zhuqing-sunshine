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

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'storage'
      AND tablename = 'objects'
      AND policyname = 'zhuqing_data_public_read'
  ) THEN
    CREATE POLICY zhuqing_data_public_read
      ON storage.objects
      FOR SELECT
      TO anon, authenticated
      USING (bucket_id = 'zhuqing-data');
  END IF;
END
$$;
