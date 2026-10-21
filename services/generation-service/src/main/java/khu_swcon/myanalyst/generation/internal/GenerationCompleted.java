package khu_swcon.myanalyst.generation.internal;


import java.util.List;
import java.util.UUID;

/**
 * 워커 → BE. 생성된 보고서 본문과 도메인 용어. 필드 이름은 {@code contracts/generation.completed.v1.json}이 기준이다.
 */
public record GenerationCompleted(UUID jobId, int attempt, String report, List<ReportTerm> terms,
                                  double generationTimeSeconds) {
    public static final String TOPIC = "generation.completed";
}
