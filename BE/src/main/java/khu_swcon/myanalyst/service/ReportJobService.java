package khu_swcon.myanalyst.service;

import khu_swcon.myanalyst.dto.ReportDto;
import khu_swcon.myanalyst.dto.ReportJobRequestDto;
import khu_swcon.myanalyst.dto.ReportJobResponseDto;
import khu_swcon.myanalyst.entity.*;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.exception.UserNotFoundException;
import khu_swcon.myanalyst.repository.ReportJobAttemptRepository;
import khu_swcon.myanalyst.repository.ReportJobRepository;
import khu_swcon.myanalyst.repository.OutboxEventRepository;
import khu_swcon.myanalyst.observability.ReportJobMetrics;
import khu_swcon.myanalyst.observability.TraceContext;
import khu_swcon.myanalyst.repository.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;

@Service
public class ReportJobService {
    private final ReportJobRepository jobRepository;
    private final ReportJobAttemptRepository attemptRepository;
    private final OutboxEventRepository outboxEventRepository;
    private final UserRepository userRepository;
    private final ReportService reportService;
    private final ExecutorService reportJobExecutor;
    private final int maxAttempts;
    private final Duration leaseDuration;
    private final TransactionTemplate transactionTemplate;
    private final ReportJobMetrics reportJobMetrics;
    private final int outboxMaxAttempts;
    private final Map<UUID, Map<String, SseEmitter>> emitters = new ConcurrentHashMap<>();

    public ReportJobService(
            ReportJobRepository jobRepository,
            ReportJobAttemptRepository attemptRepository,
            OutboxEventRepository outboxEventRepository,
            UserRepository userRepository,
            ReportService reportService,
            ExecutorService reportJobExecutor,
            TransactionTemplate transactionTemplate,
            ReportJobMetrics reportJobMetrics,
            @Value("${app.report-jobs.max-attempts:3}") int maxAttempts,
            @Value("${app.report-jobs.lease-seconds:300}") long leaseSeconds,
            @Value("${app.report-jobs.outbox-max-attempts:5}") int outboxMaxAttempts) {
        this.jobRepository = jobRepository;
        this.attemptRepository = attemptRepository;
        this.outboxEventRepository = outboxEventRepository;
        this.userRepository = userRepository;
        this.reportService = reportService;
        this.reportJobExecutor = reportJobExecutor;
        this.transactionTemplate = transactionTemplate;
        this.reportJobMetrics = reportJobMetrics;
        this.maxAttempts = maxAttempts;
        this.leaseDuration = Duration.ofSeconds(leaseSeconds);
        this.outboxMaxAttempts = outboxMaxAttempts;
    }

    @Transactional
    public ReportJobResponseDto enqueue(ReportJobRequestDto request, String userId, String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            throw new ApiException("Idempotency-Key header is required", HttpStatus.BAD_REQUEST);
        }
        if (idempotencyKey.length() > 128) {
            throw new ApiException("Idempotency-Key must not exceed 128 characters", HttpStatus.BAD_REQUEST);
        }

        ReportJob existing = jobRepository.findByUser_UseridAndIdempotencyKey(userId, idempotencyKey)
                .orElse(null);
        if (existing != null) {
            return ReportJobResponseDto.from(existing);
        }

        User user = userRepository.findByUserid(userId)
                .orElseThrow(() -> new UserNotFoundException("User not found: " + userId));
        Instant now = Instant.now();
        ReportJob job = ReportJob.builder()
                .jobId(UUID.randomUUID())
                .user(user)
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
        ReportJob savedJob = jobRepository.save(job);
        enqueueOutboxEvent(savedJob.getJobId(), now);
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
        ReportJobResponseDto response = ReportJobResponseDto.from(job);
        afterCommitPublish(jobId, response);
        return response;
    }

    public SseEmitter subscribe(UUID jobId, String userId) {
        ReportJobResponseDto current = getJob(jobId, userId);
        SseEmitter emitter = new SseEmitter(0L);
        String subscriberId = UUID.randomUUID().toString();
        emitters.computeIfAbsent(jobId, ignored -> new ConcurrentHashMap<>()).put(subscriberId, emitter);
        emitter.onCompletion(() -> removeEmitter(jobId, subscriberId));
        emitter.onTimeout(() -> removeEmitter(jobId, subscriberId));
        send(emitter, current);
        return emitter;
    }

    @Scheduled(fixedDelayString = "${app.report-jobs.poll-interval-ms:1000}")
    public void relayOutboxEvents() {
        Instant now = Instant.now();
        outboxEventRepository.findTop10ByStatusAndAvailableAtLessThanEqualOrderByCreatedAtAsc(OutboxEventStatus.PENDING, now)
                .forEach(event -> relay(event.getEventId()));
        outboxEventRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(OutboxEventStatus.PROCESSING, now)
                .forEach(event -> relay(event.getEventId()));

        jobRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(ReportJobStatus.RUNNING, now)
                .forEach(job -> transactionTemplate.executeWithoutResult(status -> recoverExpiredJob(job.getJobId())));
    }

    private void relay(UUID eventId) {
        if (!Boolean.TRUE.equals(transactionTemplate.execute(status -> claimOutboxEvent(eventId)))) {
            return;
        }
        try {
            OutboxEvent event = outboxEventRepository.findById(eventId).orElseThrow();
            dispatch(event.getAggregateId());
            transactionTemplate.executeWithoutResult(status -> markOutboxEventPublished(eventId));
        } catch (Exception exception) {
            transactionTemplate.executeWithoutResult(status -> rescheduleOutboxEvent(eventId));
        }
    }

    private void dispatch(UUID jobId) {
        if (Boolean.TRUE.equals(transactionTemplate.execute(status -> claim(jobId)))) {
            reportJobExecutor.submit(() -> execute(jobId));
        }
    }

    private boolean claimOutboxEvent(UUID eventId) {
        OutboxEvent event = outboxEventRepository.findWithLockByEventId(eventId).orElse(null);
        if (event == null || event.getStatus() == OutboxEventStatus.PUBLISHED) {
            return false;
        }
        Instant now = Instant.now();
        if (event.getStatus() == OutboxEventStatus.PENDING && event.getAvailableAt().isAfter(now)) {
            return false;
        }
        if (event.getStatus() == OutboxEventStatus.PROCESSING && event.getLeaseExpiresAt() != null
                && event.getLeaseExpiresAt().isAfter(now)) {
            return false;
        }
        event.setStatus(OutboxEventStatus.PROCESSING);
        event.setAttemptCount(event.getAttemptCount() + 1);
        event.setLeaseExpiresAt(now.plus(Duration.ofSeconds(30)));
        return true;
    }

    private void markOutboxEventPublished(UUID eventId) {
        OutboxEvent event = outboxEventRepository.findWithLockByEventId(eventId).orElseThrow();
        event.setStatus(OutboxEventStatus.PUBLISHED);
        event.setLeaseExpiresAt(null);
        event.setPublishedAt(Instant.now());
    }

    private void rescheduleOutboxEvent(UUID eventId) {
        OutboxEvent event = outboxEventRepository.findWithLockByEventId(eventId).orElse(null);
        if (event == null || event.getStatus() == OutboxEventStatus.PUBLISHED) {
            return;
        }
        if (event.getAttemptCount() >= outboxMaxAttempts) {
            deadLetterOutboxEvent(event);
            return;
        }
        long delaySeconds = Math.min(60, 1L << Math.min(6, Math.max(0, event.getAttemptCount() - 1)));
        event.setStatus(OutboxEventStatus.PENDING);
        event.setLeaseExpiresAt(null);
        event.setAvailableAt(Instant.now().plusSeconds(delaySeconds));
    }

    private void deadLetterOutboxEvent(OutboxEvent event) {
        event.setStatus(OutboxEventStatus.DEAD);
        event.setLeaseExpiresAt(null);
        reportJobMetrics.recordOutboxDeadLettered();

        ReportJob job = jobRepository.findWithLockByJobId(event.getAggregateId()).orElse(null);
        if (job == null || job.getStatus() == ReportJobStatus.SUCCEEDED
                || job.getStatus() == ReportJobStatus.FAILED || job.getStatus() == ReportJobStatus.CANCELLED) {
            return;
        }
        Instant now = Instant.now();
        job.setStatus(ReportJobStatus.FAILED);
        job.setProgressMessage("Report request could not be dispatched after repeated failures");
        job.setLastError("Outbox event " + event.getEventId() + " exceeded " + outboxMaxAttempts + " delivery attempts");
        job.setLeaseExpiresAt(null);
        job.setUpdatedAt(now);
        finishCurrentAttempt(job, now, job.getLastError());
        reportJobMetrics.recordStatus(ReportJobStatus.FAILED.name());
        afterCommitPublish(job.getJobId(), ReportJobResponseDto.from(job));
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
        enqueueOutboxEvent(jobId, now);
        afterCommitPublish(jobId, ReportJobResponseDto.from(job));
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
            afterCommitPublish(jobId, ReportJobResponseDto.from(job));
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
        afterCommitPublish(jobId, ReportJobResponseDto.from(job));
        return true;
    }

    private void execute(UUID jobId) {
        long startedAtNanos = System.nanoTime();
        try {
            ReportJob job = transactionTemplate.execute(status -> jobRepository.findById(jobId).orElseThrow());
            TraceContext.bind(job.getTraceId());
            ReportDto request = transactionTemplate.execute(status -> requestFor(jobId));
            Report report = reportService.findGeneratedReport(jobId)
                    .orElseGet(() -> reportService.createReport(request, jobId));
            transactionTemplate.executeWithoutResult(status -> markSucceeded(jobId, report));
            reportJobMetrics.recordExecution(startedAtNanos, "succeeded");
        } catch (Exception exception) {
            transactionTemplate.executeWithoutResult(status -> markFailedAttempt(jobId, rootMessage(exception)));
            reportJobMetrics.recordExecution(startedAtNanos, "failed");
        } finally {
            TraceContext.clear();
        }
    }

    private ReportDto requestFor(UUID jobId) {
        ReportJob job = jobRepository.findById(jobId).orElseThrow();
        return ReportDto.builder()
                .userid(job.getUser().getUserid())
                .title(job.getTitle())
                .chapter(job.getChapter())
                .indicator(job.getIndicator())
                .evaluations(job.getEvaluations())
                .company(job.getCompany())
                .date(job.getDate())
                .build();
    }

    private void markSucceeded(UUID jobId, Report report) {
        ReportJob job = jobRepository.findWithLockByJobId(jobId).orElseThrow();
        if (job.getStatus() == ReportJobStatus.CANCELLED) {
            return;
        }
        Instant now = Instant.now();
        job.setStatus(ReportJobStatus.SUCCEEDED);
        job.setProgress(100);
        job.setProgressMessage("Report generated");
        job.setReport(report);
        job.setLeaseExpiresAt(null);
        job.setUpdatedAt(now);
        finishCurrentAttempt(job, now, null);
        reportJobMetrics.recordStatus(ReportJobStatus.SUCCEEDED.name());
        afterCommitPublish(jobId, ReportJobResponseDto.from(job));
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
            enqueueOutboxEvent(jobId, job.getNextAttemptAt());
            reportJobMetrics.recordStatus(ReportJobStatus.RETRYING.name());
        }
        job.setUpdatedAt(now);
        afterCommitPublish(jobId, ReportJobResponseDto.from(job));
    }

    private void enqueueOutboxEvent(UUID jobId, Instant availableAt) {
        outboxEventRepository.save(OutboxEvent.builder()
                .eventId(UUID.randomUUID())
                .aggregateId(jobId)
                .eventType("REPORT_REQUESTED")
                .payload("{\"jobId\":\"" + jobId + "\"}")
                .status(OutboxEventStatus.PENDING)
                .attemptCount(0)
                .availableAt(availableAt)
                .createdAt(Instant.now())
                .build());
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
        return jobRepository.findByJobIdAndUser_Userid(jobId, userId)
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

    private void afterCommitPublish(UUID jobId, ReportJobResponseDto response) {
        // This implementation is deliberately best-effort: job state remains authoritative in PostgreSQL.
        org.springframework.transaction.support.TransactionSynchronizationManager.registerSynchronization(
                new org.springframework.transaction.support.TransactionSynchronization() {
                    @Override public void afterCommit() { publish(jobId, response); }
                });
    }

    private void publish(UUID jobId, ReportJobResponseDto response) {
        Map<String, SseEmitter> subscribers = emitters.get(jobId);
        if (subscribers != null) subscribers.forEach((id, emitter) -> send(emitter, response, id, jobId));
    }

    private void send(SseEmitter emitter, ReportJobResponseDto response) {
        send(emitter, response, null, null);
    }

    private void send(SseEmitter emitter, ReportJobResponseDto response, String subscriberId, UUID jobId) {
        try {
            emitter.send(SseEmitter.event().name("report-job").data(response));
        } catch (IOException exception) {
            if (subscriberId != null) removeEmitter(jobId, subscriberId);
        }
    }

    private void removeEmitter(UUID jobId, String subscriberId) {
        Map<String, SseEmitter> subscribers = emitters.get(jobId);
        if (subscribers != null) {
            subscribers.remove(subscriberId);
            if (subscribers.isEmpty()) emitters.remove(jobId);
        }
    }
}
