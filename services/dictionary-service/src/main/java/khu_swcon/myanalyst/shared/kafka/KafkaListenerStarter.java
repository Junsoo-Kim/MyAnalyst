package khu_swcon.myanalyst.shared.kafka;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Kafka 리스너를 애플리케이션 기동과 분리해 백그라운드에서 시작한다(BE의 같은 이름 클래스와 같은 이유:
 * 브로커 주소를 해석할 수 없을 때 컨텍스트 시작이 실패해 조회 API까지 뜨지 않는 것을 막는다).
 * 이 서비스는 소비만 하므로 토픽은 만들지 않는다. 토픽은 발행하는 서비스(BE)가 만든다.
 */
@Component
public class KafkaListenerStarter {
    private static final Logger log = LoggerFactory.getLogger(KafkaListenerStarter.class);

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerStarter(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @Scheduled(initialDelay = 0, fixedDelayString = "${app.kafka.listener-starter.retry-interval-ms:10000}")
    public void startStoppedListeners() {
        for (MessageListenerContainer container : registry.getListenerContainers()) {
            if (container.isRunning()) {
                continue;
            }
            try {
                container.start();
                log.info("Kafka 리스너 시작: {}", container.getListenerId());
            } catch (RuntimeException exception) {
                log.warn("Kafka 리스너 {} 시작 실패, 다음 주기에 재시도: {}", container.getListenerId(), exception.getMessage());
            }
        }
    }
}
