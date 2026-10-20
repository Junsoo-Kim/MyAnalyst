package khu_swcon.myanalyst.generation.internal;

import khu_swcon.myanalyst.generation.ReportJobStatusChanged;
import khu_swcon.myanalyst.shared.kafka.KafkaTopics;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

import java.util.Map;

/**
 * 생성 모듈이 발행하는 토픽. 토픽은 발행하는 모듈이 소유하고 선언한다.
 */
@Configuration
public class GenerationKafkaTopics {

    @Bean
    public KafkaAdmin.NewTopics generationTopics(
            @Value("${app.kafka.topic-partitions:3}") int partitions,
            @Value("${app.kafka.topic-replicas:1}") int replicas) {
        return new KafkaAdmin.NewTopics(
                KafkaTopics.topic(ReportGenerationRequested.TOPIC, partitions, replicas, Map.of()),
                KafkaTopics.deadLetterTopic(ReportGenerationRequested.TOPIC, partitions, replicas),
                KafkaTopics.topic(ReportJobStatusChanged.TOPIC, partitions, replicas, Map.of()),
                KafkaTopics.deadLetterTopic(ReportJobStatusChanged.TOPIC, partitions, replicas));
    }
}
