package khu_swcon.myanalyst.generation.internal;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import khu_swcon.myanalyst.generation.ReportJobService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/**
 * Saga의 마지막 단계: report-service가 저장을 마치고 발행한 {@code report.created}를 받아 Job을 완료한다.
 * 이 토픽에는 삭제(ReportDeleted)도 같은 key로 오므로 {@code event-type}이 ReportCreated이고 generationJobId가
 * 있는 것만 본다. 저장 명령 없이 만들어진 보고서(이전 단계 데이터)나 이미 끝난 Job이면 아무 일도 하지 않는다(멱등).
 */
@Component
public class ReportCreatedListener {
    static final String TOPIC = "report.created";

    @JsonIgnoreProperties(ignoreUnknown = true)
    record ReportCreated(Integer reportId, UUID generationJobId) {
    }

    private final ReportJobService reportJobService;
    private final ObjectMapper objectMapper;

    public ReportCreatedListener(ReportJobService reportJobService, ObjectMapper objectMapper) {
        this.reportJobService = reportJobService;
        this.objectMapper = objectMapper;
    }

    @KafkaListener(topics = TOPIC, groupId = "generation")
    public void on(ConsumerRecord<?, ?> record) throws IOException {
        Header type = record.headers().lastHeader("event-type");
        if (type == null || !"ReportCreated".equals(new String(type.value(), StandardCharsets.UTF_8))) {
            return;
        }
        byte[] value = record.value() instanceof byte[] bytes
                ? bytes : String.valueOf(record.value()).getBytes(StandardCharsets.UTF_8);
        ReportCreated event = objectMapper.readValue(value, ReportCreated.class);
        if (event.generationJobId() != null) {
            reportJobService.onReportSaved(event.generationJobId(), event.reportId());
        }
    }
}
