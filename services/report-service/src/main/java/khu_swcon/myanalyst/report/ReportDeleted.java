package khu_swcon.myanalyst.report;

import org.springframework.modulith.events.Externalized;

/**
 * 보고서가 삭제됐다는 도메인 이벤트. {@link ReportCreated}와 <b>같은 토픽, 같은 key(reportId)</b>로 나간다.
 * compacted 토픽에서 key별 마지막 이벤트가 삭제로 남으므로 재생해도 삭제 상태가 유지된다. 소비자는
 * {@code event-type} 헤더(ReportCreated / ReportDeleted)로 둘을 구분한다. (5단계 전에는 별도 토픽
 * report.deleted로 나갔다.) 계약 예시: {@code contracts/report.deleted.v1.json}.
 */
@Externalized(ReportCreated.TOPIC + "::#{#this.reportId().toString()}")
public record ReportDeleted(Integer reportId) {
}
