package khu_swcon.myanalyst.generation;

import khu_swcon.myanalyst.generation.internal.RagReportClient;
import khu_swcon.myanalyst.generation.internal.ReportGenerationRequested;
import khu_swcon.myanalyst.generation.internal.ReportJob;
import khu_swcon.myanalyst.generation.internal.ReportJobAttempt;
import khu_swcon.myanalyst.generation.internal.ReportJobAttemptRepository;
import khu_swcon.myanalyst.generation.internal.ReportJobMetrics;
import khu_swcon.myanalyst.generation.internal.ReportJobRepository;
import khu_swcon.myanalyst.report.GeneratedReport;
import khu_swcon.myanalyst.report.ReportService;
import khu_swcon.myanalyst.shared.ApiException;
import khu_swcon.myanalyst.shared.observability.TraceContext;
import khu_swcon.myanalyst.user.UserNotFoundException;
import khu_swcon.myanalyst.user.UserService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;

/**
 * 보고서 생성 모듈의 공개 API. Job 상태 변화는 {@link ReportJobStatusChanged} 이벤트로만 내보내고,
 * 이를 SSE로 전달하는 일은 알림 모듈이 맡는다.
 */
@Service
public class ReportJobService {
    private final ReportJobRepository jobRepository;
    private final ReportJobAttemptRepository attemptRepository;
    private final UserService userService;
    private final ReportService reportService;
    private final RagReportClient ragReportClient;
    private final ExecutorService reportJobExecutor;
    private final TransactionTemplate transactionTemplate;
    private final ReportJobMetrics reportJobMetrics;
    private final ApplicationEventPublisher events;
    private final int maxAttempts;
    private final Duration leaseDuration;

    public ReportJobService(
            ReportJobRepository jobRepository,
            ReportJobAttemptRepository attemptRepository,
            UserService userService,
            ReportService reportService,
            RagReportClient ragReportClient,
            ExecutorService reportJobExecutor,
            TransactionTemplate transactionTemplate,
            ReportJobMetrics reportJobMetrics,
            ApplicationEventPublisher events,
            @Value("${app.report-jobs.max-attempts:3}") int maxAttempts,
            @Value("${app.report-jobs.lease-seconds:300}") long leaseSeconds) {
        this.jobRepository = jobRepository;
        this.attemptRepository = attemptRepository;
        this.userService = userService;
        this.reportService = reportService;
        this.ragReportClient = ragReportClient;
        this.reportJobExecutor = reportJobExecutor;
        this.transactionTemplate = transactionTemplate;
        this.reportJobMetrics = reportJobMetrics;
        this.events = events;
        this.maxAttempts = maxAttempts;
        this.leaseDuration = Duration.ofSeconds(leaseSeconds);
    }

    public ReportJobResponseDto enqueue(ReportJobRequestDto request, String userId, String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException("Idempotency-Key header is required", HttpStatus.BAD_REQUEST);
        }
        if (idempotencyKey.length() > 128) {
            throw new ApiException("Idempotency-Key must not exceed 128 characters", HttpStatus.BAD_REQUEST);
        }

        ReportJob existing = jobRepository.findByUserIdAndIdempotencyKey(userId, idempotencyKey)
                .orElse(null);
        if (existing != null) {
            return ReportJobResponseDto.from(existing);
        }

        try {
            return transactionTemplate.execute(status -> createJob(request, userId, idempotencyKey));
        } catch (DataIntegrityViolationException raceLost) {
            ReportJob winner = jobRepository.findByUserIdAndIdempotencyKey(userId, idempotencyKey)
                    .orElseThrow(() -> raceLost);
            return ReportJobResponseDto.from(winner);
        }
    }

    private ReportJobResponseDto createJob(ReportJobRequestDto request, String userId, String idempotencyKey) {
        if (!userService.exists(userId)) {
            throw new UserNotFoundException("User not found: " + userId);
        }
        Instant now = Instant.now();
        ReportJob job = ReportJob.builder()
                .jobId(UUID.randomUUID())
                .userId(userId)
                .idempotencyKey(idempotencyKey)
                .traceId(TraceContext.currentTraceId())
                .status(ReportJobStatus.QUEUED)
                .progress(0)
                .progressMessage("Queued")
                .attemptCount(0)
                .maxAttempts(maxAttempts)
                .nextAttemptAt(now)
                .createdAt(now)
                .updatedAt(now)
                .title(request.getTitle())
                .chapter(request.getChapter())
                .indicator(defaultValue(request.getIndicator(), "none"))
                .evaluations(defaultValue(request.getEvaluations(), ""))
                .company(request.getCompany())
                .date(request.getDate())
                .build();
        // 동시에 같은 Idempotency-Key로 들어온 다른 요청이 먼저 커밋되면 유니크 제약
        // 위반으로 여기서 실패한다 — saveAndFlush로 즉시 반영해 그 실패를 이 트랜잭션
        // 안에서 바로 확인한다(지연 flush면 이 메서드가 반환된 뒤에야 터진다).
        ReportJob savedJob = jobRepository.saveAndFlush(job);
        // 같은 트랜잭션에서 발행하므로 Modulith 이벤트 레지스트리에 Job과 함께 커밋되고(Outbox),
        // 커밋 후 Kafka로 나간다. 브로커가 내려가 있어도 요청은 202로 끝나고 발행은 나중에 재시도된다.
        events.publishEvent(new ReportGenerationRequested(savedJob.getJobId()));
        reportJobMetrics.recordStatus(ReportJobStatus.QUEUED.name());
        return ReportJobResponseDto.from(savedJob);
    }

    @Transactional(readOnly = true)
    public ReportJobResponseDto getJob(UUID jobId, String userId) {
        return ReportJobResponseDto.from(findOwnedJob(jobId, userId));
    }

    @Transactional
    public ReportJobResponseDto cancel(UUID jobId, String userId) {
        ReportJob job = findOwnedJob(jobId, userId);
        if (job.getStatus() == ReportJobStatus.SUCCEEDED || job.getStatus() == ReportJobStatus.FAILED) {
            throw new ApiException("Completed jobs cannot be cancelled", HttpStatus.CONFLICT);
        }
        job.setStatus(ReportJobStatus.CANCELLED);
        job.setProgressMessage("Cancelled by user");
        Instant now = Instant.now();
        job.setLeaseExpiresAt(null);
        job.setUpdatedAt(now);
        finishCurrentAttempt(job, now, "Cancelled by user");
        reportJobMetrics.recordStatus(ReportJobStatus.CANCELLED.name());
        return publishStatus(job);
    }

    /**
     * Kafka {@code generation.requested}를 소비한다. claim과 실행은 각자 트랜잭션을 열기 때문에 이 리스너
     * 자체는 트랜잭션 없이 둔다. claim이 비관적 락으로 멱등하므로 같은 메시지가 다시 와도 Job은 한 번만
     * 실행된다. 예외가 나면 공통 에러 핸들러가 재시도 후 DLT로 보낸다.
     */
    @KafkaListener(topics = ReportGenerationRequested.TOPIC, groupId = "generation-dispatcher")
    public void on(ReportGenerationRequested event) {
        dispatch(event.jobId());
    }

    /**
     * 백오프 시간이 지난 RETRYING Job을 다시 큐에 넣고, lease가 만료된 RUNNING Job을 복구한다.
     * 실행은 직접 하지 않고 {@link ReportGenerationRequested}를 다시 발행해 최초 실행과 같은 Kafka 경로를 탄다.
     */
    @Scheduled(fixedDelayString = "${app.report-jobs.poll-interval-ms:1000}")
    public void dispatchDueRetries() {
        Instant now = Instant.now();
        jobRepository.findTop10ByStatusInAndNextAttemptAtLessThanEqualOrderByCreatedAtAsc(List.of(ReportJobStatus.RETRYING), now)
                .forEach(job -> transactionTemplate.executeWithoutResult(status -> requeue(job.getJobId())));
        jobRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(ReportJobStatus.RUNNING, now)
                .forEach(job -> transactionTemplate.executeWithoutResult(status -> recoverExpiredJob(job.getJobId())));
    }

    /**
     * RETRYING → QUEUED로 바꾸고 생성 요청을 같은 트랜잭션에서 발행한다. 상태를 바꿔 두므로 다음 폴링에서
     * 같은 Job을 또 발행하지 않는다.
     */
    private void requeue(UUID jobId) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElse(null);
        Instant now = Instant.now();
        if (job == null || job.getStatus() != ReportJobStatus.RETRYING || job.getNextAttemptAt().isAfter(now)) {
            return;
        }
        job.setStatus(ReportJobStatus.QUEUED);
        job.setProgressMessage("Requeued for retry");
        job.setUpdatedAt(now);
        events.publishEvent(new ReportGenerationRequested(jobId));
        publishStatus(job);
    }

    private void dispatch(UUID jobId) {
        if (Boolean.TRUE.equals(transactionTemplate.execute(status -> claim(jobId)))) {
            reportJobExecutor.submit(() -> execute(jobId));
        }
    }

    boolean claimForTest(UUID jobId) {
        return Boolean.TRUE.equals(transactionTemplate.execute(status -> claim(jobId)));
    }

    private void recoverExpiredJob(UUID jobId) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElse(null);
        Instant now = Instant.now();
        if (job == null || job.getStatus() != ReportJobStatus.RUNNING || job.getLeaseExpiresAt() == null
                || job.getLeaseExpiresAt().isAfter(now)) {
            return;
        }
        job.setStatus(ReportJobStatus.RETRYING);
        job.setProgressMessage("Recovering after an expired worker lease");
        job.setLeaseExpiresAt(null);
        job.setNextAttemptAt(now);
        job.setUpdatedAt(now);
        finishCurrentAttempt(job, now, "Worker lease expired");
        publishStatus(job);
    }

    private boolean claim(UUID jobId) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElse(null);
        if (job == null || job.getStatus() == ReportJobStatus.CANCELLED
                || job.getStatus() == ReportJobStatus.SUCCEEDED || job.getStatus() == ReportJobStatus.FAILED) {
            return false;
        }
        Instant now = Instant.now();
        if (job.getStatus() == ReportJobStatus.RUNNING && job.getLeaseExpiresAt() != null
                && job.getLeaseExpiresAt().isAfter(now)) {
            return false;
        }
        if ((job.getStatus() == ReportJobStatus.QUEUED || job.getStatus() == ReportJobStatus.RETRYING)
                && job.getNextAttemptAt().isAfter(now)) {
            return false;
        }
        if (job.getAttemptCount() >= job.getMaxAttempts()) {
            job.setStatus(ReportJobStatus.FAILED);
            job.setProgressMessage("Retry limit exceeded");
            job.setUpdatedAt(now);
            publishStatus(job);
            return false;
        }

        job.setAttemptCount(job.getAttemptCount() + 1);
        job.setStatus(ReportJobStatus.RUNNING);
        job.setProgress(10);
        job.setProgressMessage("Generating report");
        job.setLeaseExpiresAt(now.plus(leaseDuration));
        job.setUpdatedAt(now);
        attemptRepository.save(ReportJobAttempt.builder()
                .job(job)
                .attemptNumber(job.getAttemptCount())
                .startedAt(now)
                .build());
        reportJobMetrics.recordStatus(ReportJobStatus.RUNNING.name());
        publishStatus(job);
        return true;
    }

    private void execute(UUID jobId) {
        long startedAtNanos = System.nanoTime();
        try {
            ReportJob job = transactionTemplate.execute(status -> jobRepository.findById(jobId).orElseThrow());
            TraceContext.bind(job.getTraceId());
            // 이전 시도가 보고서 저장 직후 중단됐다면 RAG를 다시 호출하지 않고 저장된 결과로 완료한다.
            Integer reportId = reportService.findReportIdByGenerationJobId(jobId)
                    .orElseGet(() -> reportService.saveGeneratedReport(generate(job)));
            transactionTemplate.executeWithoutResult(status -> markSucceeded(jobId, reportId));
            reportJobMetrics.recordExecution(startedAtNanos, "succeeded");
        } catch (Exception exception) {
            transactionTemplate.executeWithoutResult(status -> markFailedAttempt(jobId, rootMessage(exception)));
            reportJobMetrics.recordExecution(startedAtNanos, "failed");
        } finally {
            TraceContext.clear();
        }
    }

    private GeneratedReport generate(ReportJob job) {
        RagReportClient.GeneratedContent generated = ragReportClient.generate(job);
        return new GeneratedReport(
                job.getJobId(),
                job.getUserId(),
                job.getTitle(),
                job.getChapter(),
                job.getIndicator(),
                job.getCompany(),
                job.getDate(),
                generated.report(),
                generated.terms());
    }

    private void markSucceeded(UUID jobId, Integer reportId) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElseThrow();
        if (job.getStatus() == ReportJobStatus.CANCELLED) {
            return;
        }
        Instant now = Instant.now();
        job.setStatus(ReportJobStatus.SUCCEEDED);
        job.setProgress(100);
        job.setProgressMessage("Report generated");
        job.setReportId(reportId);
        job.setLeaseExpiresAt(null);
        job.setUpdatedAt(now);
        finishCurrentAttempt(job, now, null);
        reportJobMetrics.recordStatus(ReportJobStatus.SUCCEEDED.name());
        publishStatus(job);
    }

    private void markFailedAttempt(UUID jobId, String error) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElse(null);
        if (job == null || job.getStatus() == ReportJobStatus.CANCELLED) {
            return;
        }
        Instant now = Instant.now();
        job.setLastError(error);
        job.setLeaseExpiresAt(null);
        finishCurrentAttempt(job, now, error);
        if (job.getAttemptCount() >= job.getMaxAttempts()) {
            job.setStatus(ReportJobStatus.FAILED);
            job.setProgressMessage("Report generation failed");
            reportJobMetrics.recordStatus(ReportJobStatus.FAILED.name());
        } else {
            long delaySeconds = Math.min(60, 5L * (1L << Math.max(0, job.getAttemptCount() - 1)));
            job.setStatus(ReportJobStatus.RETRYING);
            job.setProgressMessage("Retrying after a transient error");
            job.setNextAttemptAt(now.plusSeconds(delaySeconds));
            reportJobMetrics.recordStatus(ReportJobStatus.RETRYING.name());
        }
        job.setUpdatedAt(now);
        publishStatus(job);
    }

    private void finishCurrentAttempt(ReportJob job, Instant finishedAt, String error) {
        attemptRepository.findTopByJobOrderByAttemptNumberDesc(job).ifPresent(attempt -> {
            if (attempt.getFinishedAt() == null) {
                attempt.setFinishedAt(finishedAt);
                attempt.setError(error);
            }
        });
    }

    private ReportJob findOwnedJob(UUID jobId, String userId) {
        return jobRepository.findByJobIdAndUserId(jobId, userId)
                .orElseThrow(() -> new ApiException("Report job not found", HttpStatus.NOT_FOUND));
    }

    private static String defaultValue(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String rootMessage(Exception exception) {
        Throwable cause = exception;
        while (cause.getCause() != null) cause = cause.getCause();
        String message = cause.getMessage() == null ? cause.getClass().getSimpleName() : cause.getMessage();
        return message.length() > 2000 ? message.substring(0, 2000) : message;
    }

    /**
     * 현재 트랜잭션 안에서 상태 변경 이벤트를 발행한다. 알림 모듈의 리스너는 커밋 이후에만 받으므로
     * 롤백된 상태가 SSE로 나가지 않는다.
     */
    private ReportJobResponseDto publishStatus(ReportJob job) {
        ReportJobResponseDto response = ReportJobResponseDto.from(job);
        events.publishEvent(new ReportJobStatusChanged(response));
        return response;
    }
}
