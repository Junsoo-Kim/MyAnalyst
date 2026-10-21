-- MSA stage 5, one-time: reconcile the report copies kept by dictionary-service and chat-service with the
-- reports table (stage 5 still shares one PostgreSQL instance, so this can run as a single script).
--
-- Why: the services build their copies from the compacted report.created topic. Two kinds of reports are not
-- represented correctly there:
--   * reports saved before Kafka (stage 1) were never published, so no copy is created;
--   * deletions before stage 5 went to the old report.deleted topic, so replaying report.created brings those
--     reports back as copies.
-- Run after both services have started (Hibernate creates the tables) and caught up on report.created.
-- Idempotent: safe to run again.
--
--   docker exec -i myanalyst-postgres psql -U postgres -d myanalystdb < scripts/migrate/stage5_report_copies.sql

BEGIN;

INSERT INTO dictionary_reports (report_id, user_id)
SELECT r.reportid, r.userid FROM reports r
ON CONFLICT (report_id) DO NOTHING;

INSERT INTO chat_reports (report_id, user_id, content)
SELECT r.reportid, r.userid, r.content FROM reports r
ON CONFLICT (report_id) DO NOTHING;

DELETE FROM dictionary WHERE reportid NOT IN (SELECT reportid FROM reports);
DELETE FROM dictionary_reports WHERE report_id NOT IN (SELECT reportid FROM reports);
DELETE FROM chats WHERE reportid NOT IN (SELECT reportid FROM reports);
DELETE FROM chat_reports WHERE report_id NOT IN (SELECT reportid FROM reports);

COMMIT;
