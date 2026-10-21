package khu_swcon.myanalyst.generation.internal;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Component
public class ReportJobMetrics {
    private final MeterRegistry meterRegistry;

    public ReportJobMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void recordStatus(String status) {
        meterRegistry.counter("report.jobs.transitions", "status", status).increment();
    }

    /** 시도 시작(워커의 STARTED)부터 결과 수신까지. */
    public void recordExecution(Duration elapsed, String result) {
        Timer.builder("report.job.execution")
                .tag("result", result)
                .register(meterRegistry)
                .record(elapsed);
    }
}
