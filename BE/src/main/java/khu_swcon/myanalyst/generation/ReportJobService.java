package khu_swcon.myanalyst.generation;

import khu_swcon.myanalyst.generation.internal.GenerationCompleted;
import khu_swcon.myanalyst.generation.internal.GenerationFailed;
import khu_swcon.myanalyst.generation.internal.GenerationProgressed;
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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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
import java.util.Optional;
import java.util.UUID;

/**
 * 보고서 생성 모듈의 공개 API이자 생성 Job의 상태 기계.
 *
 * <p>실제 생성은 Python generation-worker가 한다. 이 클래스는 Job을 만들고 {@code generation.requested}를
 * 발행한 뒤, 워커가 돌려주는 {@code generation.progressed/completed/failed}로 상태를 옮긴다:
 * <pre>
 * QUEUED ──STARTED──▶ RUNNING ──completed──▶ SUCCEEDED
 *    ▲                  │  └──failed / lease 만료──▶ RETRYING ──(백오프 후 재발행)──┘
 *    └──────────────────┘                              └── 시도 횟수 초과 ──▶ FAILED
 * </pre>
 * 워커가 내려가 있으면 요청은 Kafka에 남고 Job은 QUEUED로 기다린다. 워커가 돌아오면 그대로 처리된다.
 * 메시지는 최소 한 번 이상 오므로 모든 전이는 "현재 상태 + 시도 번호"를 확인한 뒤에만 일어난다.
 * Job 상태 변화는 {@link ReportJobStatusChanged}로만 내보내고, SSE 전달은 알림 모듈이 맡는다.
 */
@Service
public class ReportJobService {
    private static final Logger log = LoggerFactory.getLogger(ReportJobService.class);

    private final ReportJobRepository jobRepository;
    private final ReportJobAttemptRepository attemptRepository;
    private final ReportService reportService;
    private final TransactionTemplate transactionTemplate;
    private final ReportJobMetrics reportJobMetrics;
    private final ApplicationEventPublisher events;
    private final int maxAttempts;
    private final Duration leaseDuration;

    public ReportJobService(
            ReportJobRepository jobRepository,
            ReportJobAttemptRepository attemptRepository,
            ReportService reportService,
            TransactionTemplate transactionTemplate,
            ReportJobMetrics reportJobMetrics,
            ApplicationEventPublisher events,
            @Value("${app.report-jobs.max-attempts:3}") int maxAttempts,
            @Value("${app.report-jobs.lease-seconds:300}") long leaseSeconds) {
        this.jobRepository = jobRepository;
        this.attemptRepository = attemptRepository;
        this.reportService = reportService;
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
        // 커밋 후 Kafka로 나간다. 브로커나 워커가 내려가 있어도 요청은 202로 끝난다.
        events.publishEvent(ReportGenerationRequested.of(savedJob, 1));
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

    // --- 워커 이벤트 ---------------------------------------------------------------------------

    /**
     * {@code STARTED}면 시도를 시작하고(RUNNING, lease 설정), 그 밖의 단계는 진행률을 갱신하며 lease를 늘린다.
     * 워커는 섹션마다 이 이벤트를 보내므로, 이벤트가 끊긴 채 lease가 지나면 워커가 죽은 것으로 보고 재시도한다.
     */
    @KafkaListener(topics = GenerationProgressed.TOPIC, groupId = "generation-tracker")
    public void on(GenerationProgressed event) {
        if (GenerationProgressed.STARTED.equals(event.stage())) {
            transactionTemplate.execute(status -> startAttempt(event.jobId(), event.attempt()));
        } else {
            transactionTemplate.executeWithoutResult(status -> recordProgress(event));
        }
    }

    /**
     * 보고서를 저장하고 Job을 완료한다. 보고서 저장은 생성 Job ID로 멱등하므로 같은 완료 이벤트가 다시 와도
     * 보고서는 하나만 생긴다. 이미 끝났거나 취소된 Job의 완료는 무시한다.
     */
    @KafkaListener(topics = GenerationCompleted.TOPIC, groupId = "generation-tracker")
    public void on(GenerationCompleted event) {
        ReportJob job = transactionTemplate.execute(status -> jobRepository.findById(event.jobId()).orElse(null));
        if (job == null || isTerminal(job.getStatus())) {
            log.info("job={} attempt={}: completion ignored (status={})", event.jobId(), event.attempt(),
                    job == null ? "missing" : job.getStatus());
            return;
        }
        Integer reportId = reportService.saveGeneratedReport(new GeneratedReport(
                job.getJobId(), job.getUserId(), job.getTitle(), job.getChapter(), job.getIndicator(),
                job.getCompany(), job.getDate(), event.report(), event.terms() == null ? List.of() : event.terms()));
        transactionTemplate.executeWithoutResult(status -> markSucceeded(event.jobId(), event.attempt(), reportId));
    }

    @KafkaListener(topics = GenerationFailed.TOPIC, groupId = "generation-tracker")
    public void on(GenerationFailed event) {
        transactionTemplate.executeWithoutResult(status ->
                markFailedAttempt(event.jobId(), event.attempt(), event.error(), event.retryable()));
    }

    /** 동시성 테스트용: 같은 STARTED가 여러 번(여러 스레드에서) 와도 시도는 한 번만 시작되는지 확인한다. */
    boolean startAttemptForTest(UUID jobId, int attempt) {
        return Boolean.TRUE.equals(transactionTemplate.execute(status -> startAttempt(jobId, attempt)));
    }

    private boolean startAttempt(UUID jobId, int attempt) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElse(null);
        if (job == null || isTerminal(job.getStatus())) {
            return false;
        }
        Instant now = Instant.now();
        if (job.getStatus() == ReportJobStatus.RUNNING && job.getAttemptCount() == attempt) {
            // 같은 요청이 다시 전달되어 워커가 한 번 더 시작했다. 상태는 그대로 두고 lease만 늘린다.
            job.setLeaseExpiresAt(now.plus(leaseDuration));
            return false;
        }
        if (job.getStatus() != ReportJobStatus.QUEUED || attempt != job.getAttemptCount() + 1) {
            log.info("job={} attempt={}: stale STARTED ignored (status={}, attemptCount={})",
                    jobId, attempt, job.getStatus(), job.getAttemptCount());
            return false;
        }
        job.setAttemptCount(attempt);
        job.setStatus(ReportJobStatus.RUNNING);
        job.setProgress(10);
        job.setProgressMessage("Generating report");
        job.setLeaseExpiresAt(now.plus(leaseDuration));
        job.setUpdatedAt(now);
        attemptRepository.save(ReportJobAttempt.builder()
                .job(job)
                .attemptNumber(attempt)
                .startedAt(now)
                .build());
        reportJobMetrics.recordStatus(ReportJobStatus.RUNNING.name());
        publishStatus(job);
        return true;
    }

    private void recordProgress(GenerationProgressed event) {
        ReportJob job = jobRepository.findWithLockByJobId(event.jobId()).orElse(null);
        if (job == null || job.getStatus() != ReportJobStatus.RUNNING || job.getAttemptCount() != event.attempt()) {
            return;
        }
        Instant now = Instant.now();
        job.setProgress(Math.max(job.getProgress(), Math.min(99, event.progress())));
        job.setProgressMessage(event.message());
        job.setLeaseExpiresAt(now.plus(leaseDuration));
        job.setUpdatedAt(now);
        publishStatus(job);
    }

    private void markSucceeded(UUID jobId, int attempt, Integer reportId) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElseThrow();
        if (isTerminal(job.getStatus())) {
            return;
        }
        Instant now = Instant.now();
        job.setStatus(ReportJobStatus.SUCCEEDED);
        job.setAttemptCount(Math.max(job.getAttemptCount(), attempt));
        job.setProgress(100);
        job.setProgressMessage("Report generated");
        job.setReportId(reportId);
        job.setLeaseExpiresAt(null);
        job.setUpdatedAt(now);
        finishCurrentAttempt(job, now, null)
                .ifPresent(started -> reportJobMetrics.recordExecution(Duration.between(started.getStartedAt(), now), "succeeded"));
        reportJobMetrics.recordStatus(ReportJobStatus.SUCCEEDED.name());
        publishStatus(job);
    }

    private void markFailedAttempt(UUID jobId, int attempt, String error, boolean retryable) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElse(null);
        if (job == null || job.getStatus() != ReportJobStatus.RUNNING || job.getAttemptCount() != attempt) {
            return;
        }
        Instant now = Instant.now();
        job.setLastError(error);
        job.setLeaseExpiresAt(null);
        finishCurrentAttempt(job, now, error)
                .ifPresent(started -> reportJobMetrics.recordExecution(Duration.between(started.getStartedAt(), now), "failed"));
        if (!retryable || job.getAttemptCount() >= job.getMaxAttempts()) {
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

    // --- 재시도·복구 ----------------------------------------------------------------------------

    /**
     * 백오프 시간이 지난 RETRYING Job을 다시 큐에 넣고, lease가 만료된 RUNNING Job(워커가 죽었거나 진행 이벤트가
     * 끊긴 Job)을 RETRYING으로 돌린다. QUEUED Job은 보지 않는다 — 워커가 내려가 있는 동안 요청은 Kafka에서 기다린다.
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
     * RETRYING → QUEUED로 바꾸고 다음 시도 번호로 생성 요청을 같은 트랜잭션에서 발행한다. 상태를 바꿔 두므로
     * 다음 폴링에서 같은 Job을 또 발행하지 않는다.
     */
    private void requeue(UUID jobId) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElse(null);
        Instant now = Instant.now();
        if (job == null || job.getStatus() != ReportJobStatus.RETRYING || job.getNextAttemptAt().isAfter(now)) {
            return;
        }
        job.setUpdatedAt(now);
        if (job.getAttemptCount() >= job.getMaxAttempts()) {
            job.setStatus(ReportJobStatus.FAILED);
            job.setProgressMessage("Retry limit exceeded");
            reportJobMetrics.recordStatus(ReportJobStatus.FAILED.name());
            publishStatus(job);
            return;
        }
        job.setStatus(ReportJobStatus.QUEUED);
        job.setProgressMessage("Requeued for retry");
        events.publishEvent(ReportGenerationRequested.of(job, job.getAttemptCount() + 1));
        publishStatus(job);
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

    private Optional<ReportJobAttempt> finishCurrentAttempt(ReportJob job, Instant finishedAt, String error) {
        return attemptRepository.findTopByJobOrderByAttemptNumberDesc(job)
                .filter(attempt -> attempt.getFinishedAt() == null)
                .map(attempt -> {
                    attempt.setFinishedAt(finishedAt);
                    attempt.setError(error);
                    return attempt;
                });
    }

    private ReportJob findOwnedJob(UUID jobId, String userId) {
        return jobRepository.findByJobIdAndUserId(jobId, userId)
                .orElseThrow(() -> new ApiException("Report job not found", HttpStatus.NOT_FOUND));
    }

    private static boolean isTerminal(ReportJobStatus status) {
        return status == ReportJobStatus.SUCCEEDED || status == ReportJobStatus.FAILED
                || status == ReportJobStatus.CANCELLED;
    }

    private static String defaultValue(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    /**
     * 현재 트랜잭션 안에서 상태 변경 이벤트를 발행한다. Kafka로는 커밋 이후에만 나가므로
     * 롤백된 상태가 SSE로 나가지 않는다.
     */
    private ReportJobResponseDto publishStatus(ReportJob job) {
        ReportJobResponseDto response = ReportJobResponseDto.from(job);
        events.publishEvent(new ReportJobStatusChanged(response));
        return response;
    }
}
