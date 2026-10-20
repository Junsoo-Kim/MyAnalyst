package khu_swcon.myanalyst.shared.kafka;

import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.config.TopicBuilder;

import java.util.Map;

/**
 * 토픽과 그 DLT를 같은 파티션 수로 만든다. DeadLetterPublishingRecoverer는 기본적으로 원래 레코드와 같은
 * 파티션 번호로 {@code <topic>.DLT}에 보내므로 파티션 수가 같아야 한다.
 */
public final class KafkaTopics {
    public static final String DLT_SUFFIX = ".DLT";

    private KafkaTopics() {
    }

    public static NewTopic topic(String name, int partitions, int replicas, Map<String, String> configs) {
        return TopicBuilder.name(name).partitions(partitions).replicas(replicas).configs(configs).build();
    }

    public static NewTopic deadLetterTopic(String name, int partitions, int replicas) {
        return TopicBuilder.name(name + DLT_SUFFIX).partitions(partitions).replicas(replicas).build();
    }
}
