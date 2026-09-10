package khu_swcon.myanalyst.service;

import khu_swcon.myanalyst.dto.ReportJobRequestDto;
import khu_swcon.myanalyst.dto.ReportJobResponseDto;
import khu_swcon.myanalyst.entity.*;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.observability.ReportJobMetrics;
import khu_swcon.myanalyst.repository.OutboxEventRepository;
import khu_swcon.myanalyst.repository.ReportJobAttemptRepository;
import khu_swcon.myanalyst.repository.ReportJobRepository;
import khu_swcon.myanalyst.repository.UserRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.function.Consumer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class ReportJobServiceTest {
    private static final int MAX_ATTEMPTS = 3;
    private static final int OUTBOX_MAX_ATTEMPTS = 3;

    private ReportJobRepository jobRepository;
    private ReportJobAttemptRepository attemptRepository;
    private OutboxEventRepository outboxEventRepository;
    private UserRepository userRepository;
    private ReportService reportService;
    private ExecutorService reportJobExecutor;
    private TransactionTemplate transactionTemplate;
    private ReportJobMetrics reportJobMetrics;
    private ReportJobService service;

    @BeforeEach
    void setUp() {
        jobRepository = mock(ReportJobRepository.class);
        attemptRepository = mock(ReportJobAttemptRepository.class);
        outboxEventRepository = mock(OutboxEventRepository.class);
        userRepository = mock(UserRepository.class);
        reportService = mock(ReportService.class);
        reportJobExecutor = mock(ExecutorService.class);
        transactionTemplate = mock(TransactionTemplate.class);
        reportJobMetrics = mock(ReportJobMetrics.class);

        TransactionStatus status = mock(TransactionStatus.class);
        when(transactionTemplate.execute(any())).thenAnswer(invocation -> {
            TransactionCallback<?> callback = invocation.getArgument(0);
            return callback.doInTransaction(status);
        });
        doAnswer(invocation -> {
            Consumer<TransactionStatus> callback = invocation.getArgument(0);
            callback.accept(status);
            return null;
        }).when(transactionTemplate).executeWithoutResult(any());

        when(attemptRepository.save(any())).thenAnswer(invocation -> invocation.getArgument(0));

        service = new ReportJobService(
                jobRepository, attemptRepository, outboxEventRepository, userRepository,
                reportService, reportJobExecutor, transactionTemplate, reportJobMetrics,
                MAX_ATTEMPTS, 300, OUTBOX_MAX_ATTEMPTS);

        TransactionSynchronizationManager.initSynchronization();
    }

    @AfterEach
    void tearDown() {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.clearSynchronization();
        }
    }

    private User user(String userid) {
        return User.builder().userid(userid).build();
    }

    private ReportJobRequestDto request() {
        ReportJobRequestDto dto = new ReportJobRequestDto();
        dto.setTitle("title");
        dto.setChapter("2");
        dto.setIndicator("none");
        dto.setEvaluations("");
        dto.setCompany("셀트리온");
        dto.setDate("24년 4분기");
        return dto;
    }

    @Test
    void enqueue_requiresIdempotencyKey() {
        assertThatThrownBy(() -> service.enqueue(request(), "u1", ""))
                .isInstanceOf(ApiException.class);
        verifyNoInteractions(jobRepository);
    }

    @Test
    void enqueue_returnsExistingJob_onDuplicateIdempotencyKey() {
        ReportJob existing = ReportJob.builder()
                .jobId(UUID.randomUUID()).user(user("u1")).status(ReportJobStatus.QUEUED)
                .traceId("t").createdAt(Instant.now()).updatedAt(Instant.now()).build();
        when(jobRepository.findByUser_UseridAndIdempotencyKey("u1", "key-1")).thenReturn(Optional.of(existing));

        ReportJobResponseDto response = service.enqueue(request(), "u1", "key-1");

        assertThat(response.getJobId()).isEqualTo(existing.getJobId());
        verify(jobRepository, never()).save(any());
        verify(outboxEventRepository, never()).save(any());
    }

    @Test
    void enqueue_createsJobAndOutboxEvent_onFirstRequest() {
        when(jobRepository.findByUser_UseridAndIdempotencyKey("u1", "key-1")).thenReturn(Optional.empty());
        when(userRepository.findByUserid("u1")).thenReturn(Optional.of(user("u1")));
        when(jobRepository.save(any())).thenAnswer(invocation -> invocation.getArgument(0));

        ReportJobResponseDto response = service.enqueue(request(), "u1", "key-1");

        assertThat(response.getStatus()).isEqualTo(ReportJobStatus.QUEUED);
        ArgumentCaptor<OutboxEvent> captor = ArgumentCaptor.forClass(OutboxEvent.class);
        verify(outboxEventRepository).save(captor.capture());
        assertThat(captor.getValue().getEventType()).isEqualTo("REPORT_REQUESTED");
        assertThat(captor.getValue().getStatus()).isEqualTo(OutboxEventStatus.PENDING);
    }

    @Test
    void relayOutboxEvents_dispatchesAndExecutesJobExactlyOnce() {
        UUID jobId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).user(user("u1")).status(ReportJobStatus.QUEUED)
                .attemptCount(0).maxAttempts(MAX_ATTEMPTS).nextAttemptAt(Instant.now().minusSeconds(1))
                .traceId("t").title("t").company("c").date("d")
                .createdAt(Instant.now()).updatedAt(Instant.now()).build();
        OutboxEvent event = OutboxEvent.builder()
                .eventId(eventId).aggregateId(jobId).eventType("REPORT_REQUESTED")
                .payload("{}").status(OutboxEventStatus.PENDING).attemptCount(0)
                .availableAt(Instant.now().minusSeconds(1)).createdAt(Instant.now()).build();

        when(outboxEventRepository.findTop10ByStatusAndAvailableAtLessThanEqualOrderByCreatedAtAsc(eq(OutboxEventStatus.PENDING), any()))
                .thenReturn(List.of(event));
        when(outboxEventRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(OutboxEventStatus.PROCESSING), any()))
                .thenReturn(List.of());
        when(jobRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(ReportJobStatus.RUNNING), any()))
                .thenReturn(List.of());
        when(outboxEventRepository.findWithLockByEventId(eventId)).thenReturn(Optional.of(event));
        when(outboxEventRepository.findById(eventId)).thenReturn(Optional.of(event));
        when(jobRepository.findWithLockByJobId(jobId)).thenReturn(Optional.of(job));
        when(jobRepository.findById(jobId)).thenReturn(Optional.of(job));

        Report report = Report.builder().reportid(42).build();
        when(reportService.findGeneratedReport(jobId)).thenReturn(Optional.empty());
        when(reportService.createReport(any(), eq(jobId))).thenReturn(report);
        when(reportJobExecutor.submit(any(Runnable.class))).thenAnswer(invocation -> {
            ((Runnable) invocation.getArgument(0)).run();
            return null;
        });

        service.relayOutboxEvents();

        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.SUCCEEDED);
        assertThat(job.getAttemptCount()).isEqualTo(1);
        assertThat(event.getStatus()).isEqualTo(OutboxEventStatus.PUBLISHED);
        verify(reportService, times(1)).createReport(any(), eq(jobId));
    }

    @Test
    void relayOutboxEvents_deadLettersEventAndFailsJob_afterRepeatedDispatchFailures() {
        UUID jobId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).user(user("u1")).status(ReportJobStatus.QUEUED)
                .attemptCount(0).maxAttempts(MAX_ATTEMPTS).nextAttemptAt(Instant.now())
                .traceId("t").title("t").company("c").date("d")
                .createdAt(Instant.now()).updatedAt(Instant.now()).build();
        OutboxEvent event = OutboxEvent.builder()
                .eventId(eventId).aggregateId(jobId).eventType("REPORT_REQUESTED")
                .payload("{}").status(OutboxEventStatus.PENDING).attemptCount(OUTBOX_MAX_ATTEMPTS - 1)
                .availableAt(Instant.now().minusSeconds(1)).createdAt(Instant.now()).build();

        when(outboxEventRepository.findTop10ByStatusAndAvailableAtLessThanEqualOrderByCreatedAtAsc(eq(OutboxEventStatus.PENDING), any()))
                .thenReturn(List.of(event));
        when(outboxEventRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(OutboxEventStatus.PROCESSING), any()))
                .thenReturn(List.of());
        when(jobRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(ReportJobStatus.RUNNING), any()))
                .thenReturn(List.of());
        when(outboxEventRepository.findWithLockByEventId(eventId)).thenReturn(Optional.of(event));
        when(outboxEventRepository.findById(eventId)).thenReturn(Optional.empty());
        when(jobRepository.findWithLockByJobId(jobId)).thenReturn(Optional.of(job));

        service.relayOutboxEvents();

        assertThat(event.getStatus()).isEqualTo(OutboxEventStatus.DEAD);
        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.FAILED);
        assertThat(job.getLastError()).contains(eventId.toString());
        verify(reportJobMetrics).recordOutboxDeadLettered();
        verify(reportJobExecutor, never()).submit(any(Runnable.class));
    }

    @Test
    void relayOutboxEvents_reschedulesWithoutDeadLettering_beforeAttemptLimit() {
        UUID jobId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        OutboxEvent event = OutboxEvent.builder()
                .eventId(eventId).aggregateId(jobId).eventType("REPORT_REQUESTED")
                .payload("{}").status(OutboxEventStatus.PENDING).attemptCount(0)
                .availableAt(Instant.now().minusSeconds(1)).createdAt(Instant.now()).build();

        when(outboxEventRepository.findTop10ByStatusAndAvailableAtLessThanEqualOrderByCreatedAtAsc(eq(OutboxEventStatus.PENDING), any()))
                .thenReturn(List.of(event));
        when(outboxEventRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(OutboxEventStatus.PROCESSING), any()))
                .thenReturn(List.of());
        when(jobRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(ReportJobStatus.RUNNING), any()))
                .thenReturn(List.of());
        when(outboxEventRepository.findWithLockByEventId(eventId)).thenReturn(Optional.of(event));
        when(outboxEventRepository.findById(eventId)).thenReturn(Optional.empty());

        service.relayOutboxEvents();

        assertThat(event.getStatus()).isEqualTo(OutboxEventStatus.PENDING);
        assertThat(event.getAttemptCount()).isEqualTo(1);
        verify(jobRepository, never()).findWithLockByJobId(any());
        verify(reportJobMetrics, never()).recordOutboxDeadLettered();
    }

    @Test
    void relayOutboxEvents_recoversRunningJobWithExpiredLease() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).user(user("u1")).status(ReportJobStatus.RUNNING)
                .attemptCount(1).maxAttempts(MAX_ATTEMPTS).nextAttemptAt(Instant.now())
                .leaseExpiresAt(Instant.now().minusSeconds(5))
                .traceId("t").title("t").company("c").date("d")
                .createdAt(Instant.now()).updatedAt(Instant.now()).build();

        when(outboxEventRepository.findTop10ByStatusAndAvailableAtLessThanEqualOrderByCreatedAtAsc(eq(OutboxEventStatus.PENDING), any()))
                .thenReturn(List.of());
        when(outboxEventRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(OutboxEventStatus.PROCESSING), any()))
                .thenReturn(List.of());
        when(jobRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(ReportJobStatus.RUNNING), any()))
                .thenReturn(List.of(job));
        when(jobRepository.findWithLockByJobId(jobId)).thenReturn(Optional.of(job));

        service.relayOutboxEvents();

        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.RETRYING);
        assertThat(job.getLeaseExpiresAt()).isNull();
        verify(outboxEventRepository).save(any());
    }

    @Test
    void cancel_marksJobCancelled_andFinishesAttempt() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).user(user("u1")).status(ReportJobStatus.QUEUED)
                .traceId("t").createdAt(Instant.now()).updatedAt(Instant.now()).build();
        when(jobRepository.findByJobIdAndUser_Userid(jobId, "u1")).thenReturn(Optional.of(job));

        ReportJobResponseDto response = service.cancel(jobId, "u1");

        assertThat(response.getStatus()).isEqualTo(ReportJobStatus.CANCELLED);
        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.CANCELLED);
    }

    @Test
    void cancel_rejectsAlreadyCompletedJob() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).user(user("u1")).status(ReportJobStatus.SUCCEEDED)
                .traceId("t").createdAt(Instant.now()).updatedAt(Instant.now()).build();
        when(jobRepository.findByJobIdAndUser_Userid(jobId, "u1")).thenReturn(Optional.of(job));

        assertThatThrownBy(() -> service.cancel(jobId, "u1")).isInstanceOf(ApiException.class);
    }
}
