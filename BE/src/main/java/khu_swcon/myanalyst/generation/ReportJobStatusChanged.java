package khu_swcon.myanalyst.generation;

import org.springframework.modulith.events.Externalized;

/**
 * Job 상태가 바뀔 때마다 발행된다. Kafka {@value #TOPIC} 토픽(key: jobId)으로 나가고,
 * 알림 모듈이 받아 SSE 구독자에게 전달한다.
 */
@Externalized(ReportJobStatusChanged.TOPIC + "::#{#this.job().getJobId().toString()}")
public record ReportJobStatusChanged(ReportJobResponseDto job) {
    public static final String TOPIC = "job.status-changed";
}
