package khu_swcon.myanalyst.generation.internal;

import java.util.UUID;

/**
 * Job 생성과 같은 트랜잭션에서 발행된다. Modulith 이벤트 레지스트리가 이 발행 기록을 Job과 함께
 * 커밋하므로, 커밋 직후 프로세스가 죽어도 재기동 시 다시 전달된다(기존 자체 Outbox의 역할).
 */
public record ReportGenerationRequested(UUID jobId) {
}
