package khu_swcon.myanalyst.generation.internal;

import org.springframework.modulith.events.Externalized;

import java.util.UUID;

/**
 * Job 생성(또는 재시도 예약)과 같은 트랜잭션에서 발행된다. Modulith 이벤트 레지스트리가 발행 기록을 Job과 함께
 * 커밋하고, 커밋 후 Kafka {@value #TOPIC} 토픽으로 내보낸다(Transactional Outbox). key는 jobId라
 * 같은 Job의 메시지는 한 파티션에서 순서대로 처리된다.
 */
@Externalized(ReportGenerationRequested.TOPIC + "::#{#this.jobId().toString()}")
public record ReportGenerationRequested(UUID jobId) {
    public static final String TOPIC = "generation.requested";
}
