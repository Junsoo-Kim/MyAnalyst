package khu_swcon.myanalyst.generation.internal;

import java.util.UUID;

/**
 * 워커 → BE. {@code stage=STARTED}는 시도 시작 신호이고, 이후 섹션 진행 이벤트는 lease를 늘리는 heartbeat 역할도 한다.
 * 필드 이름은 {@code contracts/generation.progressed.v1.json}이 기준이다.
 */
public record GenerationProgressed(UUID jobId, int attempt, String stage, int progress, String message) {
    public static final String TOPIC = "generation.progressed";
    public static final String STARTED = "STARTED";
}
