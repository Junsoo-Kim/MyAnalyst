package khu_swcon.myanalyst.shared.events;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

/**
 * 비동기 모듈 이벤트 리스너(@ApplicationModuleListener, @Async)가 쓸 전용 스레드 풀.
 *
 * <p>생성 모듈이 자체 Executor 빈(reportJobExecutor)을 등록하면 Spring Boot는 기본 applicationTaskExecutor를
 * 만들지 않는다. 그러면 @Async가 단일 스레드인 스케줄러로 떨어져, 이벤트 처리와 @Scheduled 작업이
 * 서로를 기다리게 된다. 그래서 명시적으로 지정한다.
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
