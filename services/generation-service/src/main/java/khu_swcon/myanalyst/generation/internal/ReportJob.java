package khu_swcon.myanalyst.generation.internal;

import khu_swcon.myanalyst.generation.ReportJobStatus;
import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "report_jobs", uniqueConstraints = @UniqueConstraint(
        name = "uk_report_job_user_idempotency", columnNames = {"userid", "idempotency_key"}))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ReportJob {

    @Id
    @Column(name = "job_id", nullable = false, updatable = false)
    private UUID jobId;

    // 다른 모듈의 엔티티 대신 ID만 보관한다. 모듈(이후 서비스) 사이에는 FK를 두지 않는다.
    @Column(name = "userid", nullable = false, length = 20)
    private String userId;

    @Column(name = "idempotency_key", nullable = false, length = 128)
    private String idempotencyKey;

    @Column(name = "trace_id", nullable = false, length = 64)
    private String traceId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private ReportJobStatus status;

    @Column(nullable = false)
    private int progress;

    @Column(name = "progress_message", length = 500)
    private String progressMessage;

    @Column(nullable = false)
    private int attemptCount;

    @Column(nullable = false)
    private int maxAttempts;

    @Column(name = "next_attempt_at", nullable = false)
    private Instant nextAttemptAt;

    @Column(name = "lease_expires_at")
    private Instant leaseExpiresAt;

    @Column(name = "last_error", columnDefinition = "TEXT")
    private String lastError;

    @Column(name = "report_id")
    private Integer reportId;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private Long version;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String title;

    @Column(columnDefinition = "TEXT")
    private String chapter;

    @Column(columnDefinition = "TEXT")
    private String indicator;

    @Column(columnDefinition = "TEXT")
    private String evaluations;

    @Column(columnDefinition = "TEXT")
    private String company;

    @Column(name = "analysis_date", columnDefinition = "TEXT")
    private String date;
}
