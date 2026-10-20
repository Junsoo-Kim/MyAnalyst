package khu_swcon.myanalyst.generation.internal;

import java.util.UUID;

/**
 * 워커 → BE. 이번 시도가 실패했다. 재시도할지는 BE가 시도 횟수로 정한다({@code retryable=false}면 바로 FAILED).
 * 필드 이름은 {@code contracts/generation.failed.v1.json}이 기준이다.
 */
public record GenerationFailed(UUID jobId, int attempt, String error, boolean retryable) {
    public static final String TOPIC = "generation.failed";
}
