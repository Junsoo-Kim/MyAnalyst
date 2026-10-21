#!/usr/bin/env bash
# MSA stage 6, one-time: move each service's tables from the shared database (myanalystdb) into its own database
# in the same PostgreSQL instance (decision D6).
#
# Order:
#   1. Stop everything that writes to myanalystdb: be, user-service, dictionary-service, chat-service
#      (kafka, postgres and redis keep running).
#   2. Run this script.
#   3. Start the stage 6 services (generation-service, report-service, and the others with their new database URLs).
#
# The script refuses to run when the shared database still has incomplete event publications (they would be lost:
# each service now has its own event_publication table) or when a target table already has rows.
# myanalystdb is left untouched so the old stack can be started again; drop it once the new one is verified.
#
#   PG_CONTAINER=myanalyst-postgres scripts/migrate/stage6_split_databases.sh
set -euo pipefail

PG_CONTAINER=${PG_CONTAINER:-myanalyst-postgres}
SOURCE_DB=${SOURCE_DB:-myanalystdb}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

psql_in() {  # psql_in <database> [psql args...]
  local db=$1; shift
  docker exec -i "$PG_CONTAINER" psql -U postgres -d "$db" -v ON_ERROR_STOP=1 "$@"
}

scalar() {  # scalar <database> <sql>
  psql_in "$1" -tA -c "$2"
}

table_exists() {  # table_exists <database> <table>
  [ "$(scalar "$1" "SELECT to_regclass('public.$2') IS NOT NULL")" = "t" ]
}

echo "== 1. preconditions ($SOURCE_DB)"
if table_exists "$SOURCE_DB" event_publication; then
  incomplete=$(scalar "$SOURCE_DB" "SELECT count(*) FROM event_publication WHERE completion_date IS NULL")
  echo "   incomplete event publications: $incomplete"
  if [ "$incomplete" != "0" ]; then
    echo "   abort: start the old services once more so they deliver these events, then stop them and retry" >&2
    exit 1
  fi
fi

echo "== 2. reconcile report copies in the shared database (stage 5 script)"
psql_in "$SOURCE_DB" -q < "$SCRIPT_DIR/stage5_report_copies.sql"

echo "== 3. create the per-service databases"
psql_in postgres -q < "$SCRIPT_DIR/../postgres/init-databases.sql"

# database:table[,table...]
MAPPING="user_db:users report_db:reports generation_db:report_jobs,report_job_attempt chat_db:chats,chat_reports dictionary_db:dictionary,dictionary_reports"

for entry in $MAPPING; do
  db=${entry%%:*}
  for table in $(echo "${entry#*:}" | tr ',' ' '); do
    if table_exists "$db" "$table" && [ "$(scalar "$db" "SELECT count(*) FROM $table")" != "0" ]; then
      echo "   abort: $db.$table already has rows" >&2
      exit 1
    fi
  done
done

echo "== 4. copy tables (schema + data + owned sequences)"
for entry in $MAPPING; do
  db=${entry%%:*}
  dump_args=()
  for table in $(echo "${entry#*:}" | tr ',' ' '); do
    if table_exists "$SOURCE_DB" "$table"; then
      dump_args+=(-t "public.$table")
      # A service may already have created the empty table (ddl-auto) — the dump recreates it.
      if table_exists "$db" "$table"; then
        psql_in "$db" -q -c "DROP TABLE $table CASCADE"
      fi
    else
      echo "   $SOURCE_DB.$table does not exist, skipped (the service creates it)"
    fi
  done
  if [ ${#dump_args[@]} -gt 0 ]; then
    docker exec "$PG_CONTAINER" pg_dump -U postgres -d "$SOURCE_DB" --no-owner --no-privileges "${dump_args[@]}" \
      | psql_in "$db" -q > /dev/null
  fi
done

echo "== 5. generation_db: allow the new SAVING status"
# Hibernate creates a CHECK constraint listing the enum values and ddl-auto=update never changes it.
psql_in generation_db -q -c "ALTER TABLE report_jobs DROP CONSTRAINT IF EXISTS report_jobs_status_check"

echo "== 6. row counts (source -> target)"
for entry in $MAPPING; do
  db=${entry%%:*}
  for table in $(echo "${entry#*:}" | tr ',' ' '); do
    if table_exists "$SOURCE_DB" "$table"; then
      echo "   $table: $(scalar "$SOURCE_DB" "SELECT count(*) FROM $table") -> $db $(scalar "$db" "SELECT count(*) FROM $table")"
    fi
  done
done
echo "done. $SOURCE_DB was not modified except for step 2."
