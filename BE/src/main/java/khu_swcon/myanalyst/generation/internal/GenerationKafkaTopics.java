package khu_swcon.myanalyst.generation.internal;

import khu_swcon.myanalyst.generation.ReportJobStatusChanged;
import khu_swcon.myanalyst.shared.kafka.KafkaTopics;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

import java.util.Map;

/**
 * 생성 모듈이 발행하는 토픽과, 생성 모듈이 소비하는 워커 토픽의 DLT.
 * 토픽은 발행하는 쪽이 소유한다: generation.progressed/completed/failed는 generation-worker가 만들고,
 * 그 메시지를 소비하다 실패했을 때 쓰는 DLT는 소비하는 이 모듈이 만든다.
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
                KafkaTopics.deadLetterTopic(ReportJobStatusChanged.TOPIC, partitions, replicas),
                KafkaTopics.deadLetterTopic(GenerationProgressed.TOPIC, partitions, replicas),
                KafkaTopics.deadLetterTopic(GenerationCompleted.TOPIC, partitions, replicas),
                KafkaTopics.deadLetterTopic(GenerationFailed.TOPIC, partitions, replicas));
    }
}
