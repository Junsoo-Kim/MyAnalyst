package khu_swcon.myanalyst.report.internal;

import khu_swcon.myanalyst.report.ReportCreated;
import khu_swcon.myanalyst.report.ReportDeleted;
import khu_swcon.myanalyst.shared.kafka.KafkaTopics;
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

import java.util.Map;

/**
 * 보고서 모듈이 발행하는 토픽. report.created는 compaction으로 보고서별 최신 이벤트를 계속 보관해,
 * 소비자가 offset을 처음으로 되돌려 자기 데이터를 다시 만들 수 있게 한다.
 */
@Configuration
public class ReportKafkaTopics {

    @Bean
    public KafkaAdmin.NewTopics reportTopics(
            @Value("${app.kafka.topic-partitions:3}") int partitions,
            @Value("${app.kafka.topic-replicas:1}") int replicas) {
        return new KafkaAdmin.NewTopics(
                KafkaTopics.topic(ReportCreated.TOPIC, partitions, replicas,
                        Map.of(TopicConfig.CLEANUP_POLICY_CONFIG, TopicConfig.CLEANUP_POLICY_COMPACT)),
                KafkaTopics.deadLetterTopic(ReportCreated.TOPIC, partitions, replicas),
                KafkaTopics.topic(ReportDeleted.TOPIC, partitions, replicas, Map.of()),
                KafkaTopics.deadLetterTopic(ReportDeleted.TOPIC, partitions, replicas));
    }
}
