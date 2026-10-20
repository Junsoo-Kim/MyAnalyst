package khu_swcon.myanalyst.notification.internal;

import khu_swcon.myanalyst.generation.ReportJobResponseDto;
import khu_swcon.myanalyst.generation.ReportJobStatusChanged;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Job별 SSE 구독자를 관리한다. 생성 모듈은 이 클래스를 모르고 {@link ReportJobStatusChanged}만 발행한다.
 */
@Component
public class ReportJobEventStream {
    private final Map<UUID, Map<String, SseEmitter>> emitters = new ConcurrentHashMap<>();
    private final Map<UUID, Instant> lastSentAt = new ConcurrentHashMap<>();

    public SseEmitter subscribe(ReportJobResponseDto current) {
        UUID jobId = current.getJobId();
        SseEmitter emitter = new SseEmitter(0L);
        String subscriberId = UUID.randomUUID().toString();
        emitters.computeIfAbsent(jobId, ignored -> new ConcurrentHashMap<>()).put(subscriberId, emitter);
        emitter.onCompletion(() -> removeEmitter(jobId, subscriberId));
        emitter.onTimeout(() -> removeEmitter(jobId, subscriberId));
        lastSentAt.merge(jobId, current.getUpdatedAt(), (a, b) -> a.isAfter(b) ? a : b);
        send(emitter, current, subscriberId, jobId);
        return emitter;
    }

    /**
     * Kafka {@code job.status-changed}를 소비한다. SSE 연결은 그 연결을 받은 인스턴스에만 있으므로
     * 인스턴스마다 고유한 consumer group으로 모든 이벤트를 받고, 기동 이후 이벤트만 읽는다(latest).
     *
     * <p>같은 Job의 메시지는 jobId key로 한 파티션에서 순서대로 오지만, 발행이 비동기 풀에서 일어나므로
     * 몇 ms 차이로 커밋된 상태가 뒤바뀌어 도착할 수 있다. 이미 보낸 상태보다 오래된 것은 버린다.
     * 전송 실패는 이 구독자만 정리하고 예외를 밖으로 던지지 않는다(Job 상태의 기준은 DB, SSE는 최선 노력 전달).
     */
    @KafkaListener(
            topics = ReportJobStatusChanged.TOPIC,
            groupId = "notification-#{T(java.util.UUID).randomUUID().toString()}",
            properties = "auto.offset.reset=latest")
    public void on(ReportJobStatusChanged event) {
        ReportJobResponseDto job = event.job();
        Map<String, SseEmitter> subscribers = emitters.get(job.getJobId());
        if (subscribers == null || isStale(job)) {
            return;
        }
        subscribers.forEach((id, emitter) -> send(emitter, job, id, job.getJobId()));
    }

    private boolean isStale(ReportJobResponseDto job) {
        Instant updatedAt = job.getUpdatedAt();
        Instant previous = lastSentAt.get(job.getJobId());
        if (previous != null && updatedAt.isBefore(previous)) {
            return true;
        }
        lastSentAt.put(job.getJobId(), updatedAt);
        return false;
    }

    private void send(SseEmitter emitter, ReportJobResponseDto response, String subscriberId, UUID jobId) {
        try {
            emitter.send(SseEmitter.event().name("report-job").data(response));
        } catch (IOException | IllegalStateException exception) {
            removeEmitter(jobId, subscriberId);
        }
    }

    private void removeEmitter(UUID jobId, String subscriberId) {
        Map<String, SseEmitter> subscribers = emitters.get(jobId);
        if (subscribers != null) {
            subscribers.remove(subscriberId);
            if (subscribers.isEmpty()) {
                emitters.remove(jobId);
                lastSentAt.remove(jobId);
            }
        }
    }
}
