package khu_swcon.myanalyst.report;

import java.util.List;
import java.util.UUID;

/**
 * 보고서가 저장됐다는 도메인 이벤트. 용어 사전 모듈이 이 이벤트로 용어를 저장한다.
 */
public record ReportCreated(Integer reportId, UUID generationJobId, String userId, List<ReportTerm> terms) {
}
