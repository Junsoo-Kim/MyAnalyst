"""Experiment baseline: a consumer that handles each message synchronously inside the poll loop.

With a job longer than max.poll.interval.ms the consumer is kicked out of the group mid-job, its offset
commit fails, and the same message is delivered again -> duplicate processing.
Run inside the generation-worker image (confluent-kafka available).
"""
import sys
import time

from confluent_kafka import Consumer, KafkaException

TOPIC, GROUP = sys.argv[1], sys.argv[2]
JOB_SECONDS, RUN_SECONDS = float(sys.argv[3]), float(sys.argv[4])

events = []
c = Consumer({
    "bootstrap.servers": "kafka:19092", "group.id": GROUP, "enable.auto.commit": False,
    "auto.offset.reset": "earliest", "max.poll.interval.ms": 10000, "session.timeout.ms": 6000,
})
c.subscribe([TOPIC],
            on_assign=lambda _c, ps: events.append(("assigned", [p.partition for p in ps])),
            on_revoke=lambda _c, ps: events.append(("revoked", [p.partition for p in ps])))
deadline = time.time() + RUN_SECONDS
processed = {}
while time.time() < deadline:
    msg = c.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        events.append(("error", str(msg.error())))
        continue
    key = msg.value().decode()
    processed[key] = processed.get(key, 0) + 1
    print(f"{time.strftime('%X')} start {key} (delivery #{processed[key]})", flush=True)
    time.sleep(JOB_SECONDS)  # the long job, poll() is NOT called meanwhile
    try:
        c.commit(message=msg, asynchronous=False)
        print(f"{time.strftime('%X')} done  {key} committed", flush=True)
    except KafkaException as e:
        print(f"{time.strftime('%X')} done  {key} COMMIT FAILED: {e.args[0].str()}", flush=True)
c.close()
print("rebalance/error events:", events)
print("deliveries per message:", processed)
