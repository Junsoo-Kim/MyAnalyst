package khu_swcon.myanalyst.generation;

import khu_swcon.myanalyst.generation.ReportJobRequestDto;
import khu_swcon.myanalyst.generation.ReportJobResponseDto;
import khu_swcon.myanalyst.generation.internal.ReportJob;
import khu_swcon.myanalyst.generation.ReportJobStatus;
import khu_swcon.myanalyst.generation.internal.ReportJobRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
// DB 락·유니크 제약만 검증하는 테스트라 Kafka(토픽 생성, 리스너, 외부 발행)는 끈다.
@SpringBootTest(properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "app.kafka.listener-starter.enabled=false",
        "spring.modulith.events.externalization.enabled=false"})
class ReportJobConcurrencyIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:17-alpine");

    @Autowired
    private ReportJobService reportJobService;

    @Autowired
    private ReportJobRepository jobRepository;

    private UUID jobId;

    @BeforeEach
    void setUp() {
        // 사용자는 user-service가 소유한다(4단계). BE는 Gateway가 검증한 사용자 ID만 받으므로 사용자 행이 필요 없다.
        Instant now = Instant.now();
        ReportJob job = ReportJob.builder()
                .jobId(UUID.randomUUID())
                .userId("concurrency-user")
                .idempotencyKey("concurrency-test-key-" + UUID.randomUUID())
                .traceId("trace-1")
                .status(ReportJobStatus.QUEUED)
                .progress(0)
                .attemptCount(0)
                .maxAttempts(3)
                .nextAttemptAt(now.minusSeconds(1))
                .createdAt(now)
                .updatedAt(now)
                .title("동시성 테스트")
                .build();
        jobId = jobRepository.save(job).getJobId();
    }

    @Test
    void concurrentStartsOfTheSameAttemptStartItOnlyOnce() throws Exception {
        int workerCount = 10;
        ExecutorService pool = Executors.newFixedThreadPool(workerCount);
        CountDownLatch ready = new CountDownLatch(workerCount);
        CountDownLatch start = new CountDownLatch(1);

        List<Future<Boolean>> submitted = new java.util.ArrayList<>();
        for (int i = 0; i < workerCount; i++) {
            submitted.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                // 같은 시도의 STARTED가 동시에 여러 번 도착한 상황(재전달·중복 워커)
                return reportJobService.startAttemptForTest(jobId, 1);
            }));
        }

        ready.await(5, TimeUnit.SECONDS);
        start.countDown();

        List<Boolean> results = submitted.stream().map(future -> {
            try {
                return future.get(10, TimeUnit.SECONDS);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }).collect(Collectors.toList());
        pool.shutdown();

        long successCount = results.stream().filter(Boolean::booleanValue).count();
        assertThat(successCount).isEqualTo(1);

        ReportJob persisted = jobRepository.findById(jobId).orElseThrow();
        assertThat(persisted.getAttemptCount()).isEqualTo(1);
        assertThat(persisted.getStatus()).isEqualTo(ReportJobStatus.RUNNING);
    }

    @Test
    void tenConcurrentRequestsWithTheSameIdempotencyKeyCreateOnlyOneJob() throws Exception {
        ReportJobRequestDto request = new ReportJobRequestDto();
        request.setTitle("동시 제출 테스트");
        request.setChapter("2. 실적");
        request.setIndicator("none");
        request.setEvaluations("");
        request.setCompany("테스트회사");
        request.setDate("테스트");
        String idempotencyKey = UUID.randomUUID().toString();

        int requestCount = 10;
        ExecutorService pool = Executors.newFixedThreadPool(requestCount);
        CountDownLatch ready = new CountDownLatch(requestCount);
        CountDownLatch start = new CountDownLatch(1);

        List<Future<UUID>> submitted = new java.util.ArrayList<>();
        for (int i = 0; i < requestCount; i++) {
            submitted.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                ReportJobResponseDto response =
                        reportJobService.enqueue(request, "concurrency-user", idempotencyKey);
                return response.getJobId();
            }));
        }

        ready.await(5, TimeUnit.SECONDS);
        start.countDown();

        List<UUID> jobIds = submitted.stream().map(future -> {
            try {
                return future.get(10, TimeUnit.SECONDS);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }).collect(Collectors.toList());
        pool.shutdown();

        assertThat(jobIds).doesNotContainNull();
        assertThat(new java.util.HashSet<>(jobIds)).hasSize(1);
    }
}
