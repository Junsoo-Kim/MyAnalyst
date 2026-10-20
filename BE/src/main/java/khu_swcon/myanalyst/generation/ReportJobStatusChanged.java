package khu_swcon.myanalyst.generation;

/**
 * Job 상태가 바뀔 때마다 발행된다. 알림 모듈이 이 이벤트를 받아 SSE 구독자에게 전달한다.
 */
public record ReportJobStatusChanged(ReportJobResponseDto job) {
}
