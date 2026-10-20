package khu_swcon.myanalyst.notification.internal;

import khu_swcon.myanalyst.generation.ReportJobResponseDto;
import khu_swcon.myanalyst.generation.ReportJobStatusChanged;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Job별 SSE 구독자를 관리한다. 생성 모듈은 이 클래스를 모르고 {@link ReportJobStatusChanged}만 발행한다.
 */
@Component
public class ReportJobEventStream {
    private final Map<UUID, Map<String, SseEmitter>> emitters = new ConcurrentHashMap<>();

    public SseEmitter subscribe(ReportJobResponseDto current) {
        UUID jobId = current.getJobId();
        SseEmitter emitter = new SseEmitter(0L);
        String subscriberId = UUID.randomUUID().toString();
        emitters.computeIfAbsent(jobId, ignored -> new ConcurrentHashMap<>()).put(subscriberId, emitter);
        emitter.onCompletion(() -> removeEmitter(jobId, subscriberId));
        emitter.onTimeout(() -> removeEmitter(jobId, subscriberId));
        send(emitter, current, subscriberId, jobId);
        return emitter;
    }

    /**
     * 커밋 이후 발행 스레드에서 동기로 전달한다. 비동기로 받으면 RUNNING/SUCCEEDED 같은 연속된 상태가
     * 뒤바뀐 순서로 도착할 수 있어서다. 전송 실패는 이 구독자만 정리하고 예외를 밖으로 던지지 않는다
     * (Job 상태의 기준은 DB이고, SSE는 최선 노력 전달이다).
     */
    @TransactionalEventListener
    public void on(ReportJobStatusChanged event) {
        ReportJobResponseDto job = event.job();
        Map<String, SseEmitter> subscribers = emitters.get(job.getJobId());
        if (subscribers != null) subscribers.forEach((id, emitter) -> send(emitter, job, id, job.getJobId()));
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
            if (subscribers.isEmpty()) emitters.remove(jobId);
        }
    }
}
