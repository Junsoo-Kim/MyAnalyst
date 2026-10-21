#!/bin/bash
# Publishes Kafka health to CloudWatch every minute (systemd timer on the broker host):
#   ConsumerLag{Group}          sum of lag over all partitions of the group (groups matching GROUPS_RE)
#   DeadLetterMessages{Topic}   end offset sum of each <topic>.DLT (alarm on increase)
# DRY_RUN=1 prints the metrics instead of calling the AWS CLI.
set -euo pipefail

NAMESPACE=${NAMESPACE:-MyAnalyst/Kafka}
KAFKA_CONTAINER=${KAFKA_CONTAINER:-kafka}
BOOTSTRAP=${BOOTSTRAP:-localhost:9092}
# Durable consumer groups only. notification-<uuid> groups are per instance and left behind on restart.
GROUPS_RE=${GROUPS_RE:-^(generation-worker|generation-tracker|generation|report|dictionary|chat)$}

kafka() {
  local tool=$1
  shift
  docker exec "$KAFKA_CONTAINER" "/opt/kafka/bin/$tool" --bootstrap-server "$BOOTSTRAP" "$@"
}

put() {  # put <metric> <dimension name> <dimension value> <value>
  if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "$1 $2=$3 $4"
  else
    aws cloudwatch put-metric-data --namespace "$NAMESPACE" --metric-name "$1" \
      --dimensions "$2=$3" --value "$4" --unit Count
  fi
}

# GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG ... ; LAG is "-" before the first commit.
kafka kafka-consumer-groups.sh --describe --all-groups 2>/dev/null \
  | awk -v re="$GROUPS_RE" '$1 ~ re && NF >= 6 { seen[$1] = 1; if ($6 ~ /^[0-9]+$/) lag[$1] += $6 }
                            END { for (g in seen) printf "%s %d\n", g, lag[g] }' \
  | while read -r group lag; do put ConsumerLag Group "$group" "$lag"; done

# topic:partition:offset
kafka kafka-get-offsets.sh --topic '.*\.DLT' 2>/dev/null \
  | awk -F: 'NF == 3 { sum[$1] += $3 } END { for (t in sum) printf "%s %d\n", t, sum[t] }' \
  | while read -r topic count; do put DeadLetterMessages Topic "$topic" "$count"; done
