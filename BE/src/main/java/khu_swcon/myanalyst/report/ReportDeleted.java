package khu_swcon.myanalyst.report;

import org.springframework.modulith.events.Externalized;

/**
 * 보고서가 삭제됐다는 도메인 이벤트. Kafka {@value #TOPIC} 토픽(key: reportId)으로 나가고,
 * DB cascade 대신 채팅·용어 모듈이 이 이벤트로 각자의 데이터를 정리한다.
 */
@Externalized(ReportDeleted.TOPIC + "::#{#this.reportId().toString()}")
public record ReportDeleted(Integer reportId) {
    public static final String TOPIC = "report.deleted";
}
