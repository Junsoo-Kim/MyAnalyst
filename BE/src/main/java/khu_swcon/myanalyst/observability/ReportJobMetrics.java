package khu_swcon.myanalyst.observability;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class ReportJobMetrics {
    private final MeterRegistry meterRegistry;

    public ReportJobMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void recordStatus(String status) {
        meterRegistry.counter("report.jobs.transitions", "status", status).increment();
    }

    public void recordOutboxDeadLettered() {
        meterRegistry.counter("report.jobs.outbox.dead_lettered").increment();
    }

    public void recordExecution(long startedAtNanos, String result) {
        Timer.builder("report.job.execution")
                .tag("result", result)
                .register(meterRegistry)
                .record(System.nanoTime() - startedAtNanos, TimeUnit.NANOSECONDS);
    }
}
