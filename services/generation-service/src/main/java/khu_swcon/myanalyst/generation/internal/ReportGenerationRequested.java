package khu_swcon.myanalyst.generation.internal;

import org.springframework.modulith.events.Externalized;

import java.util.UUID;

/**
 * 생성 요청. Job 생성(또는 재시도 예약)과 같은 트랜잭션에서 발행된다. Modulith 이벤트 레지스트리가 발행 기록을
 * Job과 함께 커밋하고, 커밋 후 Kafka {@value #TOPIC} 토픽(key: jobId)으로 내보낸다(Transactional Outbox).
 *
 * <p>소비자는 Python generation-worker다. 워커는 BE DB를 보지 않으므로 생성에 필요한 입력을 모두 싣는다.
 * 필드 이름은 {@code contracts/generation.requested.v1.json}이 기준이다.
 *
 * @param attempt 이번 요청이 몇 번째 시도인지(1부터). 워커의 진행·결과 이벤트가 이 번호를 그대로 돌려주므로
 *                BE는 오래된 시도의 이벤트를 구별해 무시할 수 있다.
 */
@Externalized(ReportGenerationRequested.TOPIC + "::#{#this.jobId().toString()}")
public record ReportGenerationRequested(
        UUID jobId,
        int attempt,
        String traceId,
        String title,
        String chapter,
        String indicator,
        String evaluations,
        String company,
        String date) {

    public static final String TOPIC = "generation.requested";

    public static ReportGenerationRequested of(ReportJob job, int attempt) {
        return new ReportGenerationRequested(job.getJobId(), attempt, job.getTraceId(), job.getTitle(),
                job.getChapter(), job.getIndicator(), job.getEvaluations(), job.getCompany(), job.getDate());
    }
}
