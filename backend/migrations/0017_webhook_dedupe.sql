-- 0017: webhook replay/dup defense — a single captured-and-replayed event (or a duplicate delivery)
-- must be idempotent. Partial UNIQUE on (tenant_id, source, external_id) lets enqueue use
-- ON CONFLICT DO NOTHING. NULL external_id rows (events without a provider id) are exempt.

CREATE UNIQUE INDEX IF NOT EXISTS event_queue_dedupe_uq
    ON event_queue (tenant_id, source, external_id)
    WHERE external_id IS NOT NULL;
