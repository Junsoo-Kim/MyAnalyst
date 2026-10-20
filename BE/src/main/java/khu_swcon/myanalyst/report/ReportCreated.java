package khu_swcon.myanalyst.report;

import org.springframework.modulith.events.Externalized;

import java.util.List;
import java.util.UUID;

/**
 * 보고서가 저장됐다는 도메인 이벤트. Kafka {@value #TOPIC} 토픽(key: reportId, compacted)으로 나간다.
 *
 * <p>dictionary-service와 chat-service가 이 이벤트로 자기 사본을 만든다: 소유자(userId)로 접근 권한을 스스로
 * 판단하고(요청마다 보고서 서비스에 묻지 않는다), chat-service는 질의응답에 쓸 본문(content)을 보관한다.
 * 같은 토픽에 {@link ReportDeleted}도 같은 key로 나가므로, compaction 뒤에도 보고서별 마지막 상태(생성/삭제)가
 * 남아 소비자가 처음부터 다시 읽어도(재생) 삭제된 보고서가 되살아나지 않는다.
 * 계약 예시: {@code contracts/report.created.v1.json}.
 */
@Externalized(ReportCreated.TOPIC + "::#{#this.reportId().toString()}")
public record ReportCreated(Integer reportId, UUID generationJobId, String userId, String content,
                            List<ReportTerm> terms) {
    public static final String TOPIC = "report.created";
}
