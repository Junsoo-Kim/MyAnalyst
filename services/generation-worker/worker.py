# worker.py — generation-worker: generation.requested를 소비해 보고서를 만들고 결과를 이벤트로 돌려준다.
#
# 메시지 하나(보고서 생성)는 수 분이 걸린다. 처리하는 동안 poll()을 멈추면 max.poll.interval.ms를 넘겨
# 컨슈머 그룹에서 쫓겨나고(리밸런스) 같은 메시지가 다른 워커에게 다시 배정된다. 그래서
#   1) 메시지를 받으면 할당된 파티션을 pause하고,
#   2) 생성은 별도 스레드에서 돌리면서 메인 루프는 poll()을 계속 호출해 그룹 멤버십을 유지하고,
#   3) 끝나면 결과 이벤트를 보낸 뒤(flush) offset을 커밋하고 resume한다.
# 오프셋은 결과 이벤트가 브로커에 기록된 다음에만 커밋하므로(at-least-once), 워커가 중간에 죽으면
# 메시지는 다시 전달되고 섹션 체크포인트 덕분에 이미 만든 섹션은 다시 생성하지 않는다.
import logging
import signal
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from prometheus_client import Counter, Histogram, start_http_server
from pydantic import ValidationError

import config
import events
import llm_tasks
import pipeline
from myanalyst_common import observability

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("myanalyst.generation-worker")

JOBS = Counter("worker_jobs_total", "Generation requests handled", ["result"], registry=observability.registry)
JOB_DURATION = Histogram("worker_job_duration_seconds", "Report generation duration", registry=observability.registry,
                         buckets=(5, 15, 30, 60, 120, 300, 600, 1200))
REBALANCES = Counter("worker_rebalances_total", "Partition assignment changes", ["kind"], registry=observability.registry)


def _headers(event_type: str):
    return [("event-type", event_type.encode()), ("event-version", events.EVENT_VERSION.encode())]


class GenerationWorker:
    def __init__(self):
        self.running = True
        self.busy = threading.Event()
        self.revoked_while_busy = False
        self.consumer = Consumer({
            "bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": config.KAFKA_GROUP_ID,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            "max.poll.interval.ms": config.KAFKA_MAX_POLL_INTERVAL_MS,
            "session.timeout.ms": config.KAFKA_SESSION_TIMEOUT_MS,
        })
        self.producer = Producer({
            "bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS,
            "acks": "all",
            "enable.idempotence": True,
        })
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="generate")

    # --- topics -------------------------------------------------------------------------------
    def ensure_owned_topics(self) -> None:
        """워커가 발행하는 토픽을 만든다. 브로커가 없으면 생길 때까지 재시도한다(워커 기동이 브로커에 막히지 않게)."""
        admin = AdminClient({"bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS})
        topics = [NewTopic(t, num_partitions=config.KAFKA_TOPIC_PARTITIONS, replication_factor=config.KAFKA_TOPIC_REPLICAS)
                  for t in events.OWNED_TOPICS]
        while self.running:
            try:
                for topic, future in admin.create_topics(topics, request_timeout=10).items():
                    try:
                        future.result()
                        log.info("created topic %s", topic)
                    except KafkaException as e:
                        if e.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                            raise
                return
            except Exception as e:  # noqa: BLE001 - 브로커 미기동 등은 모두 재시도 대상
                log.warning("topic creation failed, retrying in 5s: %s", e)
                time.sleep(5)

    # --- rebalance callbacks ------------------------------------------------------------------
    def _on_assign(self, consumer, partitions):
        REBALANCES.labels(kind="assigned").inc()
        log.info("partitions assigned: %s", [f"{p.topic}-{p.partition}" for p in partitions])
        if self.busy.is_set():
            # 처리 중에 새로 배정된 파티션도 멈춰 둔다. 그렇지 않으면 poll()이 다음 메시지를 넘겨준다.
            consumer.pause(partitions)

    def _on_revoke(self, consumer, partitions):
        REBALANCES.labels(kind="revoked").inc()
        log.warning("partitions revoked: %s (busy=%s)", [f"{p.topic}-{p.partition}" for p in partitions], self.busy.is_set())
        if self.busy.is_set():
            self.revoked_while_busy = True

    # --- publishing ---------------------------------------------------------------------------
    def publish(self, topic: str, key: str, message: events._Message) -> None:
        self.producer.produce(topic, key=key.encode(), value=message.to_json_bytes(), headers=_headers(type(message).__name__))
        # 결과가 브로커에 기록된 것을 확인한 뒤에야 offset을 커밋한다.
        remaining = self.producer.flush(30)
        if remaining:
            raise RuntimeError(f"{remaining} message(s) not delivered to {topic}")

    def dead_letter(self, msg, reason: str) -> None:
        headers = list(msg.headers() or []) + [("dlt-exception-message", reason[:1000].encode())]
        self.producer.produce(msg.topic() + events.DLT_SUFFIX, key=msg.key(), value=msg.value(),
                              headers=headers, partition=msg.partition())
        self.producer.flush(30)
        log.error("dead-lettered %s-%s@%s: %s", msg.topic(), msg.partition(), msg.offset(), reason)

    # --- handling -----------------------------------------------------------------------------
    def handle(self, request: events.GenerationRequested) -> None:
        observability.set_trace_id(request.trace_id or request.job_id)
        started = time.perf_counter()
        key = request.job_id

        def progress(stage: str, percent: int, message: str) -> None:
            self.publish(events.GENERATION_PROGRESSED, key, events.GenerationProgressed(
                job_id=request.job_id, attempt=request.attempt, stage=stage, progress=percent, message=message))

        progress("STARTED", 10, f"Generating report (attempt {request.attempt})")
        try:
            report = pipeline.generate_full_report(
                title=request.title, company=request.company, date=request.date,
                chapter=request.chapter or "", indicator=request.indicator or "none",
                evaluations=request.evaluations or "", generation_job_id=request.job_id,
                on_progress=progress,
            )
            progress("TERMS", 95, "Extracting domain-specific terms")
            terms = llm_tasks.extract_domain_specific_terms(report)
            elapsed = time.perf_counter() - started
            self.publish(events.GENERATION_COMPLETED, key, events.GenerationCompleted(
                job_id=request.job_id, attempt=request.attempt, report=report,
                terms=[events.ReportTermMessage(**t) for t in terms],
                generation_time_seconds=round(elapsed, 2)))
            JOBS.labels(result="completed").inc()
            JOB_DURATION.observe(elapsed)
            log.info("job=%s attempt=%s completed in %.1fs", request.job_id, request.attempt, elapsed)
        except Exception as e:  # noqa: BLE001 - 어떤 실패든 generation-service에 알려 재시도 여부를 거기서 정하게 한다
            traceback.print_exc()
            self.publish(events.GENERATION_FAILED, key, events.GenerationFailed(
                job_id=request.job_id, attempt=request.attempt, error=f"{type(e).__name__}: {e}"[:2000], retryable=True))
            JOBS.labels(result="failed").inc()
            log.warning("job=%s attempt=%s failed: %s", request.job_id, request.attempt, e)

    def process(self, msg) -> None:
        try:
            request = events.GenerationRequested.model_validate_json(msg.value())
        except (ValidationError, ValueError) as e:
            # 형식이 깨진 메시지는 재시도해도 소용없다. DLT로 보내고 다음으로 넘어간다.
            self.dead_letter(msg, f"invalid generation.requested: {e}")
            self.consumer.commit(message=msg, asynchronous=False)
            return

        log.info("job=%s attempt=%s received from %s-%s@%s", request.job_id, request.attempt,
                 msg.topic(), msg.partition(), msg.offset())
        assignment = self.consumer.assignment()
        self.busy.set()
        self.revoked_while_busy = False
        self.consumer.pause(assignment)
        try:
            future = self.executor.submit(self.handle, request)
            while not future.done():
                # 파티션이 멈춰 있으므로 메시지는 오지 않지만, poll()이 그룹 heartbeat·리밸런스 콜백을 처리한다.
                stray = self.consumer.poll(0.5)
                if stray is not None and not stray.error():
                    # 리밸런스 직후 아직 멈추지 못한 파티션에서 온 메시지: 처리하지 않고 그 위치로 되감는다.
                    self.consumer.seek(TopicPartition(stray.topic(), stray.partition(), stray.offset()))
            future.result()
        finally:
            self.busy.clear()
            self.consumer.resume(self.consumer.assignment())

        if self.revoked_while_busy:
            # 처리 중에 파티션을 뺏겼다. 새 주인이 같은 메시지를 다시 처리하며, generation-service가 시도 번호·Job 상태로 중복을 무시한다.
            log.warning("job=%s: partition revoked during processing, skipping commit", request.job_id)
            return
        self.consumer.commit(message=msg, asynchronous=False)

    # --- main loop ----------------------------------------------------------------------------
    def run(self) -> None:
        self.ensure_owned_topics()
        self.consumer.subscribe([events.GENERATION_REQUESTED], on_assign=self._on_assign, on_revoke=self._on_revoke)
        log.info("generation-worker consuming %s as group %s", events.GENERATION_REQUESTED, config.KAFKA_GROUP_ID)
        try:
            while self.running:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        log.warning("consumer error: %s", msg.error())
                    continue
                self.process(msg)
        finally:
            self.consumer.close()
            self.executor.shutdown(wait=False)

    def stop(self, *_):
        log.info("shutdown requested")
        self.running = False


def main() -> int:
    start_http_server(config.METRICS_PORT, registry=observability.registry)
    worker = GenerationWorker()
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
