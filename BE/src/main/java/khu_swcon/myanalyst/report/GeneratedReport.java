package khu_swcon.myanalyst.report;

import java.util.List;
import java.util.UUID;

/**
 * 생성 모듈이 보고서 모듈에 저장을 요청할 때 넘기는 결과물.
 */
public record GeneratedReport(
        UUID generationJobId,
        String userId,
        String title,
        String chapter,
        String indicator,
        String company,
        String date,
        String content,
        List<ReportTerm> terms) {
}
