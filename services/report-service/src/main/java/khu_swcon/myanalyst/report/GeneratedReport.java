package khu_swcon.myanalyst.report;

import java.util.List;
import java.util.UUID;

/**
 * 저장할 생성 결과물. generation-service의 저장 명령({@code report.save-requested})에서 만든다.
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
