package khu_swcon.myanalyst.dictionary.events;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

import java.nio.charset.StandardCharsets;

/**
 * BE(보고서 모듈)가 발행하는 {@value #TOPIC} 토픽의 계약. 예시: {@code contracts/report.created.v1.json},
 * {@code contracts/report.deleted.v1.json}.
 */
public final class ReportEvents {
    public static final String TOPIC = "report.created";
    public static final String CREATED = "ReportCreated";
    public static final String DELETED = "ReportDeleted";

    private ReportEvents() {
    }

    public static String eventType(ConsumerRecord<?, ?> record) {
        Header header = record.headers().lastHeader("event-type");
        return header == null ? "" : new String(header.value(), StandardCharsets.UTF_8);
    }
}
