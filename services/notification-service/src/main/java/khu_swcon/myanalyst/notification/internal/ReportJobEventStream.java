package khu_swcon.myanalyst.notification.internal;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Job별 SSE 구독자를 관리한다. BE(생성 모듈)는 이 서비스를 모르고 {@value #TOPIC}만 발행한다.
 *
 * <p>소유권은 BE에 묻지 않는다. 구독은 요청자 ID와 함께 등록되고, 이벤트에 실린 {@code job.userId}가 같은 구독자에게만
 * 보낸다. 남의 jobId로 구독해도 연결만 열리고 아무것도 받지 못한다. 구독 직후의 현재 상태는 이 인스턴스가 마지막으로
 * 본 스냅샷이 있으면(소유자가 같을 때만) 바로 보내고, 없으면 다음 이벤트를 기다린다. 화면은 구독 전에
 * {@code GET /report-jobs/{id}}로 현재 상태를 먼저 읽고 주기적으로도 다시 읽으므로 SSE는 최선 노력 전달이다.
 */
@Component
public class ReportJobEventStream {
    static final String TOPIC = "job.status-changed";
    private static final Logger log = LoggerFactory.getLogger(ReportJobEventStream.class);
    private static final int MAX_SNAPSHOTS = 10_000;

    private record Subscriber(String userId, SseEmitter emitter) {
    }

    private record Snapshot(String userId, Instant updatedAt, JsonNode job) {
    }

    private final ObjectMapper objectMapper;
    private final Map<String, Map<SseEmitter, Subscriber>> subscribers = new ConcurrentHashMap<>();
    /** jobId → 마지막으로 본 상태. 오래된(순서가 뒤바뀐) 이벤트를 버리고, 새 구독자에게 현재 상태를 보내는 데 쓴다. */
    private final Map<String, Snapshot> snapshots = Collections.synchronizedMap(
            new LinkedHashMap<>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, Snapshot> eldest) {
                    return size() > MAX_SNAPSHOTS;
                }
            });

    public ReportJobEventStream(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public SseEmitter subscribe(String jobId, String userId) {
        SseEmitter emitter = new SseEmitter(0L);
        subscribers.computeIfAbsent(jobId, ignored -> new ConcurrentHashMap<>()).put(emitter, new Subscriber(userId, emitter));
        emitter.onCompletion(() -> removeEmitter(jobId, emitter));
        emitter.onTimeout(() -> removeEmitter(jobId, emitter));
        emitter.onError(ignored -> removeEmitter(jobId, emitter));
        Snapshot current = snapshots.get(jobId);
        if (current != null && current.userId().equals(userId)) {
            send(jobId, emitter, current.job());
        } else {
            // 보낼 상태가 없어도 응답 헤더를 바로 내보낸다(첫 이벤트 전까지 연결이 응답 없이 매달려 있지 않게).
            sendComment(jobId, emitter);
        }
        return emitter;
    }

    /**
     * Kafka {@value #TOPIC}을 소비한다. SSE 연결은 그 연결을 받은 인스턴스에만 있으므로 인스턴스마다 고유한
     * consumer group으로 모든 이벤트를 받고, 기동 이후 이벤트만 읽는다(latest).
     *
     * <p>같은 Job의 메시지는 jobId key로 한 파티션에서 순서대로 오지만, BE의 발행이 비동기 풀에서 일어나므로
     * 몇 ms 차이로 커밋된 상태가 뒤바뀌어 도착할 수 있다. 이미 본 상태보다 오래된 것은 버린다.
     * 해석할 수 없는 메시지는 로그만 남기고 넘어간다(Job 상태의 기준은 BE의 DB다).
     */
    @KafkaListener(
            topics = TOPIC,
            groupId = "notification-#{T(java.util.UUID).randomUUID().toString()}",
            properties = "auto.offset.reset=latest")
    public void on(ConsumerRecord<String, byte[]> record) {
        JsonNode job;
        String jobId;
        String userId;
        Instant updatedAt;
        try {
            job = objectMapper.readTree(record.value()).path("job");
            jobId = job.path("jobId").asText(null);
            userId = job.path("userId").asText(null);
            updatedAt = instant(job.path("updatedAt"));
        } catch (IOException | RuntimeException exception) {
            log.warn("{} 메시지 해석 실패, 건너뜀 (offset={}): {}", TOPIC, record.offset(), exception.getMessage());
            return;
        }
        if (jobId == null || userId == null || !remember(jobId, new Snapshot(userId, updatedAt, job))) {
            return;
        }
        Map<SseEmitter, Subscriber> jobSubscribers = subscribers.get(jobId);
        if (jobSubscribers == null) {
            return;
        }
        jobSubscribers.values().stream()
                .filter(subscriber -> subscriber.userId().equals(userId))
                .forEach(subscriber -> send(jobId, subscriber.emitter(), job));
    }

    /** 이미 본 상태보다 오래되지 않았으면 스냅샷으로 남기고 true. */
    private boolean remember(String jobId, Snapshot next) {
        synchronized (snapshots) {
            Snapshot previous = snapshots.get(jobId);
            if (previous != null && next.updatedAt() != null && previous.updatedAt() != null
                    && next.updatedAt().isBefore(previous.updatedAt())) {
                return false;
            }
            snapshots.put(jobId, next);
            return true;
        }
    }

    /** Jackson 설정에 따라 ISO 문자열이나 epoch 초(소수)로 온다. */
    private static Instant instant(JsonNode node) {
        if (node.isNumber()) {
            BigDecimal seconds = node.decimalValue();
            return Instant.ofEpochSecond(seconds.longValue(),
                    seconds.remainder(BigDecimal.ONE).movePointRight(9).longValue());
        }
        return node.isTextual() ? Instant.parse(node.asText()) : null;
    }

    private void send(String jobId, SseEmitter emitter, JsonNode job) {
        try {
            emitter.send(SseEmitter.event().name("report-job").data(job));
        } catch (IOException | IllegalStateException exception) {
            removeEmitter(jobId, emitter);
        }
    }

    private void sendComment(String jobId, SseEmitter emitter) {
        try {
            emitter.send(SseEmitter.event().comment("subscribed"));
        } catch (IOException | IllegalStateException exception) {
            removeEmitter(jobId, emitter);
        }
    }

    private void removeEmitter(String jobId, SseEmitter emitter) {
        subscribers.computeIfPresent(jobId, (ignored, jobSubscribers) -> {
            jobSubscribers.remove(emitter);
            return jobSubscribers.isEmpty() ? null : jobSubscribers;
        });
    }
}
