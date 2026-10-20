package khu_swcon.myanalyst.generation;

import khu_swcon.myanalyst.generation.internal.RagReportClient;
import khu_swcon.myanalyst.generation.internal.ReportGenerationRequested;
import khu_swcon.myanalyst.generation.internal.ReportJob;
import khu_swcon.myanalyst.generation.internal.ReportJobAttemptRepository;
import khu_swcon.myanalyst.generation.internal.ReportJobMetrics;
import khu_swcon.myanalyst.generation.internal.ReportJobRepository;
import khu_swcon.myanalyst.report.ReportService;
import khu_swcon.myanalyst.shared.ApiException;
import khu_swcon.myanalyst.user.UserService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
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
import static org.mockito.ArgumentMatchers.isA;
import static org.mockito.Mockito.*;

class ReportJobServiceTest {
    private static final int MAX_ATTEMPTS = 3;

    private ReportJobRepository jobRepository;
    private ReportJobAttemptRepository attemptRepository;
    private UserService userService;
    private ReportService reportService;
    private RagReportClient ragReportClient;
    private ExecutorService reportJobExecutor;
    private TransactionTemplate transactionTemplate;
    private ReportJobMetrics reportJobMetrics;
    private ApplicationEventPublisher events;
    private ReportJobService service;

    @BeforeEach
    void setUp() {
        jobRepository = mock(ReportJobRepository.class);
        attemptRepository = mock(ReportJobAttemptRepository.class);
        userService = mock(UserService.class);
        reportService = mock(ReportService.class);
        ragReportClient = mock(RagReportClient.class);
        reportJobExecutor = mock(ExecutorService.class);
        transactionTemplate = mock(TransactionTemplate.class);
        reportJobMetrics = mock(ReportJobMetrics.class);
        events = mock(ApplicationEventPublisher.class);

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
                jobRepository, attemptRepository, userService, reportService, ragReportClient,
                reportJobExecutor, transactionTemplate, reportJobMetrics, events,
                MAX_ATTEMPTS, 300);
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

    private ReportJob queuedJob(UUID jobId) {
        return ReportJob.builder()
                .jobId(jobId).userId("u1").status(ReportJobStatus.QUEUED)
                .attemptCount(0).maxAttempts(MAX_ATTEMPTS).nextAttemptAt(Instant.now().minusSeconds(1))
                .traceId("t").title("t").company("c").date("d")
                .createdAt(Instant.now()).updatedAt(Instant.now()).build();
    }

    private void runSubmittedTasksInline() {
        when(reportJobExecutor.submit(any(Runnable.class))).thenAnswer(invocation -> {
            ((Runnable) invocation.getArgument(0)).run();
            return null;
        });
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
                .jobId(UUID.randomUUID()).userId("u1").status(ReportJobStatus.QUEUED)
                .traceId("t").createdAt(Instant.now()).updatedAt(Instant.now()).build();
        when(jobRepository.findByUserIdAndIdempotencyKey("u1", "key-1")).thenReturn(Optional.of(existing));

        ReportJobResponseDto response = service.enqueue(request(), "u1", "key-1");

        assertThat(response.getJobId()).isEqualTo(existing.getJobId());
        verify(jobRepository, never()).saveAndFlush(any());
        verify(events, never()).publishEvent(isA(ReportGenerationRequested.class));
    }

    @Test
    void enqueue_createsJobAndPublishesGenerationRequest_onFirstRequest() {
        when(jobRepository.findByUserIdAndIdempotencyKey("u1", "key-1")).thenReturn(Optional.empty());
        when(userService.exists("u1")).thenReturn(true);
        when(jobRepository.saveAndFlush(any())).thenAnswer(invocation -> invocation.getArgument(0));

        ReportJobResponseDto response = service.enqueue(request(), "u1", "key-1");

        assertThat(response.getStatus()).isEqualTo(ReportJobStatus.QUEUED);
        ArgumentCaptor<ReportGenerationRequested> captor = ArgumentCaptor.forClass(ReportGenerationRequested.class);
        verify(events).publishEvent(captor.capture());
        assertThat(captor.getValue().jobId()).isEqualTo(response.getJobId());
    }

    @Test
    void generationRequested_dispatchesAndExecutesJobExactlyOnce() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = queuedJob(jobId);
        when(jobRepository.findWithLockByJobId(jobId)).thenReturn(Optional.of(job));
        when(jobRepository.findById(jobId)).thenReturn(Optional.of(job));
        when(reportService.findReportIdByGenerationJobId(jobId)).thenReturn(Optional.empty());
        when(ragReportClient.generate(job)).thenReturn(new RagReportClient.GeneratedContent("generated", List.of()));
        when(reportService.saveGeneratedReport(any())).thenReturn(42);
        runSubmittedTasksInline();

        service.on(new ReportGenerationRequested(jobId));

        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.SUCCEEDED);
        assertThat(job.getAttemptCount()).isEqualTo(1);
        assertThat(job.getReportId()).isEqualTo(42);
        verify(ragReportClient, times(1)).generate(job);
        verify(reportService, times(1)).saveGeneratedReport(any());
    }

    @Test
    void failedExecution_schedulesRetry_beforeAttemptLimit() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = queuedJob(jobId);
        when(jobRepository.findWithLockByJobId(jobId)).thenReturn(Optional.of(job));
        when(jobRepository.findById(jobId)).thenReturn(Optional.of(job));
        when(reportService.findReportIdByGenerationJobId(jobId)).thenReturn(Optional.empty());
        when(ragReportClient.generate(job)).thenThrow(new ApiException("rag down", org.springframework.http.HttpStatus.INTERNAL_SERVER_ERROR));
        runSubmittedTasksInline();

        service.on(new ReportGenerationRequested(jobId));

        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.RETRYING);
        assertThat(job.getLastError()).contains("rag down");
        assertThat(job.getNextAttemptAt()).isAfter(Instant.now());
        verify(reportService, never()).saveGeneratedReport(any());
    }

    @Test
    void dispatchDueRetries_recoversRunningJobWithExpiredLease() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).userId("u1").status(ReportJobStatus.RUNNING)
                .attemptCount(1).maxAttempts(MAX_ATTEMPTS).nextAttemptAt(Instant.now())
                .leaseExpiresAt(Instant.now().minusSeconds(5))
                .traceId("t").title("t").company("c").date("d")
                .createdAt(Instant.now()).updatedAt(Instant.now()).build();

        when(jobRepository.findTop10ByStatusInAndNextAttemptAtLessThanEqualOrderByCreatedAtAsc(eq(List.of(ReportJobStatus.RETRYING)), any()))
                .thenReturn(List.of());
        when(jobRepository.findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(eq(ReportJobStatus.RUNNING), any()))
                .thenReturn(List.of(job));
        when(jobRepository.findWithLockByJobId(jobId)).thenReturn(Optional.of(job));

        service.dispatchDueRetries();

        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.RETRYING);
        assertThat(job.getLeaseExpiresAt()).isNull();
        verify(events).publishEvent(isA(ReportJobStatusChanged.class));
    }

    @Test
    void cancel_marksJobCancelled_andFinishesAttempt() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).userId("u1").status(ReportJobStatus.QUEUED)
                .traceId("t").createdAt(Instant.now()).updatedAt(Instant.now()).build();
        when(jobRepository.findByJobIdAndUserId(jobId, "u1")).thenReturn(Optional.of(job));

        ReportJobResponseDto response = service.cancel(jobId, "u1");

        assertThat(response.getStatus()).isEqualTo(ReportJobStatus.CANCELLED);
        assertThat(job.getStatus()).isEqualTo(ReportJobStatus.CANCELLED);
    }

    @Test
    void cancel_rejectsAlreadyCompletedJob() {
        UUID jobId = UUID.randomUUID();
        ReportJob job = ReportJob.builder()
                .jobId(jobId).userId("u1").status(ReportJobStatus.SUCCEEDED)
                .traceId("t").createdAt(Instant.now()).updatedAt(Instant.now()).build();
        when(jobRepository.findByJobIdAndUserId(jobId, "u1")).thenReturn(Optional.of(job));

        assertThatThrownBy(() -> service.cancel(jobId, "u1")).isInstanceOf(ApiException.class);
    }
}
