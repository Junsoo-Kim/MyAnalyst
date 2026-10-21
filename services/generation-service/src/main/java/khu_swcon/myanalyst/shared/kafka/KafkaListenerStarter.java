package khu_swcon.myanalyst.shared.kafka;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Kafka 리스너를 애플리케이션 기동과 분리해 백그라운드에서 시작한다.
 *
 * <p>리스너 컨테이너를 기동 시점에 시작하면(Spring Kafka 기본값) 브로커 주소를 해석할 수 없을 때
 * ("No resolvable bootstrap urls") 컨텍스트 시작이 실패해 API 서버 전체가 뜨지 않는다. 브로커 장애가 로그인·조회까지
 * 막는 것이다. 그래서 {@code spring.kafka.listener.auto-startup=false}로 두고, 여기서 주기적으로 토픽 생성과
 * 멈춰 있는 컨테이너 시작을 재시도한다. 발행 쪽은 Modulith 이벤트 레지스트리가 미완료 발행을 다시 보내므로
 * 브로커가 돌아오면 소비·발행이 모두 이어진다.
 */
@Component
@ConditionalOnProperty(name = "app.kafka.listener-starter.enabled", havingValue = "true", matchIfMissing = true)
public class KafkaListenerStarter {
    private static final Logger log = LoggerFactory.getLogger(KafkaListenerStarter.class);

    private final KafkaListenerEndpointRegistry registry;
    private final KafkaAdmin kafkaAdmin;
    private volatile boolean topicsReady;

    public KafkaListenerStarter(KafkaListenerEndpointRegistry registry, KafkaAdmin kafkaAdmin) {
        this.registry = registry;
        this.kafkaAdmin = kafkaAdmin;
    }

    @Scheduled(initialDelay = 0, fixedDelayString = "${app.kafka.listener-starter.retry-interval-ms:10000}")
    public void startStoppedListeners() {
        if (!topicsReady) {
            topicsReady = initializeTopics();
            if (!topicsReady) {
                return;
            }
        }
        for (MessageListenerContainer container : registry.getListenerContainers()) {
            if (container.isRunning()) {
                continue;
            }
            try {
                container.start();
                log.info("Kafka 리스너 시작: {}", container.getListenerId());
            } catch (RuntimeException exception) {
                log.warn("Kafka 리스너 {} 시작 실패, 다음 주기에 재시도: {}", container.getListenerId(), rootMessage(exception));
            }
        }
    }

    private boolean initializeTopics() {
        try {
            boolean created = kafkaAdmin.initialize();
            if (!created) {
                log.warn("Kafka 토픽 확인 실패(브로커 연결 불가), 다음 주기에 재시도");
            }
            return created;
        } catch (RuntimeException exception) {
            log.warn("Kafka 토픽 확인 실패, 다음 주기에 재시도: {}", rootMessage(exception));
            return false;
        }
    }

    private static String rootMessage(Throwable throwable) {
        Throwable cause = throwable;
        while (cause.getCause() != null) cause = cause.getCause();
        return cause.getMessage();
    }
}
