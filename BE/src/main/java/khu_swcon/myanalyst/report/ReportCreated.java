package khu_swcon.myanalyst.report;

import org.springframework.modulith.events.Externalized;

import java.util.List;
import java.util.UUID;

/**
 * 보고서가 저장됐다는 도메인 이벤트. Kafka {@value #TOPIC} 토픽(key: reportId, compacted)으로 나가고,
 * 용어 사전 모듈이 이 이벤트로 용어를 저장한다. compaction으로 보고서별 최신 이벤트가 남으므로,
 * 나중에 생기는 소비자도 처음부터 읽어 자기 데이터를 만들 수 있다.
 */
@Externalized(ReportCreated.TOPIC + "::#{#this.reportId().toString()}")
public record ReportCreated(Integer reportId, UUID generationJobId, String userId, List<ReportTerm> terms) {
    public static final String TOPIC = "report.created";
}
