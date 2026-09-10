package khu_swcon.myanalyst.dto;

import khu_swcon.myanalyst.entity.ReportJob;
import khu_swcon.myanalyst.entity.ReportJobStatus;
import lombok.Builder;
import lombok.Value;

import java.time.Instant;
import java.util.UUID;

@Value
@Builder
public class ReportJobResponseDto {
    UUID jobId;
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
                .traceId(job.getTraceId())
                .status(job.getStatus())
                .progress(job.getProgress())
                .message(job.getProgressMessage())
                .attemptCount(job.getAttemptCount())
                .reportId(job.getReport() == null ? null : job.getReport().getReportid())
                .error(job.getStatus() == ReportJobStatus.FAILED ? job.getLastError() : null)
                .createdAt(job.getCreatedAt())
                .updatedAt(job.getUpdatedAt())
                .build();
    }
}
