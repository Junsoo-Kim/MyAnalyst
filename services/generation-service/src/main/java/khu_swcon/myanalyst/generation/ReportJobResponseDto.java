package khu_swcon.myanalyst.generation;

import khu_swcon.myanalyst.generation.internal.ReportJob;
import khu_swcon.myanalyst.generation.ReportJobStatus;
import lombok.Builder;
import lombok.Value;
import lombok.extern.jackson.Jacksonized;

import java.time.Instant;
import java.util.UUID;

@Value
@Builder
@Jacksonized // Kafka 메시지(ReportJobStatusChanged)에서 역직렬화할 수 있도록 빌더를 Jackson에 연결한다.
public class ReportJobResponseDto {
    UUID jobId;
    String userId; // notification-service가 SSE 구독자에게 자기 Job만 보내도록 소유자를 싣는다.
    String traceId;
    ReportJobStatus status;
    int progress;
    String message;
    int attemptCount;
    Integer reportId;
    String error;
    Instant createdAt;
    Instant updatedAt;

    public static ReportJobResponseDto from(ReportJob job) {
        return ReportJobResponseDto.builder()
                .jobId(job.getJobId())
                .userId(job.getUserId())
                .traceId(job.getTraceId())
                .status(job.getStatus())
                .progress(job.getProgress())
                .message(job.getProgressMessage())
                .attemptCount(job.getAttemptCount())
                .reportId(job.getReportId())
                .error(job.getStatus() == ReportJobStatus.FAILED ? job.getLastError() : null)
                .createdAt(job.getCreatedAt())
                .updatedAt(job.getUpdatedAt())
                .build();
    }
}
