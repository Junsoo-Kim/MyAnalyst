package khu_swcon.myanalyst.shared.kafka;

import io.micrometer.core.instrument.MeterRegistry;
import khu_swcon.myanalyst.MyanalystApplication;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaOperations;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;
import org.springframework.modulith.events.EventExternalizationConfiguration;

import java.util.Map;

@Configuration
public class KafkaMessagingConfig {
    private static final Logger log = LoggerFactory.getLogger(KafkaMessagingConfig.class);

    /**
     * 이벤트 스키마 버전. 이벤트 레코드의 필드를 호환되지 않게 바꾸면 올리고, 소비자는 이 헤더로 분기한다.
     * Python 워커(3단계) 같은 다른 언어 소비자도 클래스 정보 없이 이 두 헤더만으로 메시지를 해석한다.
     */
    static final String EVENT_VERSION = "1";

    /**
     * {@code @Externalized}가 붙은 이벤트만 내보내는 Modulith 기본 설정에 공통 헤더를 더한다.
     */
    @Bean
    public EventExternalizationConfiguration eventExternalizationConfiguration() {
        return EventExternalizationConfiguration.defaults(MyanalystApplication.class.getPackageName())
                .headers(event -> Map.of(
                        "event-type", event.getClass().getSimpleName(),
                        "event-version", EVENT_VERSION))
                .build();
    }

    /**
     * 소비 실패 시 지수 백오프로 재시도하고, 그래도 실패하면 {@code <topic>.DLT}로 보낸 뒤 다음 메시지로 넘어간다.
     * 한 메시지 때문에 파티션 전체가 막히지 않게 하고, 실패 메시지는 DLT에 남겨 원인 확인 후 다시 넣을 수 있게 한다.
     * 역직렬화(변환) 실패는 재시도해도 소용없으므로 Spring Kafka 기본 분류대로 바로 DLT로 간다.
     */
    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaOperations<Object, Object> kafkaOperations,
            MeterRegistry meterRegistry,
            @Value("${app.kafka.consumer.max-retries:3}") int maxRetries,
            @Value("${app.kafka.consumer.initial-backoff-ms:1000}") long initialBackoffMs) {
        // 목적지를 명시한다. Spring Kafka 3.x 기본값은 "<topic>-dlt"인데 토픽은 "<topic>.DLT"로 만들어 두었고,
        // 브로커 자동 생성을 꺼 두었기 때문에 이름이 어긋나면 DLT 발행이 실패하고 파티션이 그 자리에 멈춘다.
        DeadLetterPublishingRecoverer deadLetterPublisher = new DeadLetterPublishingRecoverer(kafkaOperations,
                (record, exception) -> new TopicPartition(record.topic() + KafkaTopics.DLT_SUFFIX, record.partition()));
        ConsumerRecordRecoverer recoverer = (record, exception) -> {
            log.error("Kafka 소비 최종 실패 → {}{} (partition={}, offset={}, key={}): {}",
                    record.topic(), KafkaTopics.DLT_SUFFIX, record.partition(), record.offset(), record.key(),
                    exception.getMessage());
            meterRegistry.counter("kafka.consumer.dead_lettered", "topic", record.topic()).increment();
            deadLetterPublisher.accept(record, exception);
        };
        ExponentialBackOffWithMaxRetries backOff = new ExponentialBackOffWithMaxRetries(maxRetries);
        backOff.setInitialInterval(initialBackoffMs);
        backOff.setMultiplier(2.0);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
