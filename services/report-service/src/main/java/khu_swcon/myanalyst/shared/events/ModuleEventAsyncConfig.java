package khu_swcon.myanalyst.shared.events;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

/**
 * 비동기 이벤트 리스너(Modulith의 Kafka 외부 발행, @Async)가 쓸 전용 스레드 풀.
 *
 * <p>기본 applicationTaskExecutor가 만들어지지 않는 구성(다른 Executor 빈이 있을 때)에서도 @Async가 단일 스레드인
 * 스케줄러로 떨어져 이벤트 발행과 @Scheduled 작업이 서로를 기다리지 않도록 명시적으로 지정한다.
 */
@Configuration
public class ModuleEventAsyncConfig implements AsyncConfigurer {

    @Bean(destroyMethod = "shutdown")
    public ThreadPoolTaskExecutor moduleEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("module-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        executor.initialize();
        return executor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return moduleEventExecutor();
    }
}
