package khu_swcon.myanalyst.generation.internal;

import org.springframework.modulith.events.Externalized;

import java.util.List;
import java.util.UUID;

/**
 * 보고서 저장 명령(Saga 한 단계). 워커의 완료 이벤트를 받은 트랜잭션에서 Job을 SAVING으로 바꾸며 함께 발행하고,
 * 커밋 후 Kafka {@value #TOPIC}(key: jobId)으로 나간다. report-service가 저장한 뒤 {@code report.created}에
 * 이 jobId를 {@code generationJobId}로 실어 발행하면 Job이 SUCCEEDED가 된다.
 *
 * <p>report-service는 이 서비스의 DB를 보지 않으므로 저장에 필요한 값을 모두 싣는다. 저장은 jobId로 멱등이다.
 * 필드 이름은 {@code contracts/report.save-requested.v1.json}이 기준이다.
 */
@Externalized(ReportSaveRequested.TOPIC + "::#{#this.jobId().toString()}")
public record ReportSaveRequested(
        UUID jobId,
        String userId,
        String title,
        String chapter,
        String indicator,
        String company,
        String date,
        String content,
        List<ReportTerm> terms) {

    public static final String TOPIC = "report.save-requested";

    public static ReportSaveRequested of(ReportJob job, GenerationCompleted completed) {
        return new ReportSaveRequested(job.getJobId(), job.getUserId(), job.getTitle(), job.getChapter(),
                job.getIndicator(), job.getCompany(), job.getDate(), completed.report(),
                completed.terms() == null ? List.of() : completed.terms());
    }
}
