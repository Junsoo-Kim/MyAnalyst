package khu_swcon.myanalyst.shared.kafka;

import io.micrometer.core.instrument.MeterRegistry;
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

/**
 * 소비 실패 시 지수 백오프로 재시도하고, 그래도 실패하면 {@code <topic>.DLT}(같은 파티션)로 보낸 뒤 다음 메시지로 넘어간다.
 * DLT 토픽은 BE가 원래 토픽과 같은 파티션 수로 만들어 둔다. 목적지를 명시하는 이유는 BE의 KafkaMessagingConfig와 같다.
 */
@Configuration
public class KafkaDeadLetterConfig {
    private static final Logger log = LoggerFactory.getLogger(KafkaDeadLetterConfig.class);
    public static final String DLT_SUFFIX = ".DLT";

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaOperations<Object, Object> kafkaOperations,
            MeterRegistry meterRegistry,
            @Value("${app.kafka.consumer.max-retries:3}") int maxRetries,
            @Value("${app.kafka.consumer.initial-backoff-ms:1000}") long initialBackoffMs) {
        DeadLetterPublishingRecoverer deadLetterPublisher = new DeadLetterPublishingRecoverer(kafkaOperations,
                (record, exception) -> new TopicPartition(record.topic() + DLT_SUFFIX, record.partition()));
        ConsumerRecordRecoverer recoverer = (record, exception) -> {
            log.error("Kafka 소비 최종 실패 → {}{} (partition={}, offset={}, key={}): {}",
                    record.topic(), DLT_SUFFIX, record.partition(), record.offset(), record.key(),
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
