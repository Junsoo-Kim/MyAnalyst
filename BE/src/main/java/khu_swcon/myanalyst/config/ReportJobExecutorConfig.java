package khu_swcon.myanalyst.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

@Configuration
public class ReportJobExecutorConfig {
    @Bean(destroyMethod = "shutdown")
    public ExecutorService reportJobExecutor() {
        // RAG generation is expensive; bounded concurrency prevents the API process from being exhausted.
        AtomicInteger threadNumber = new AtomicInteger();
        return Executors.newFixedThreadPool(2, runnable -> {
            Thread thread = new Thread(runnable, "report-job-" + threadNumber.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        });
    }
}
