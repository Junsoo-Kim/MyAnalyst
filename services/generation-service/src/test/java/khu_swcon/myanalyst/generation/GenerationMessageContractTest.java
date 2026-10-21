package khu_swcon.myanalyst.generation;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import khu_swcon.myanalyst.generation.internal.GenerationCompleted;
import khu_swcon.myanalyst.generation.internal.GenerationFailed;
import khu_swcon.myanalyst.generation.internal.GenerationProgressed;
import khu_swcon.myanalyst.generation.internal.ReportGenerationRequested;
import khu_swcon.myanalyst.generation.internal.ReportJob;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Spring ↔ Python generation-worker 메시지 계약. 원래 RagReportClientContractTest(HTTP /reports 요청의
 * evaluations 필드 검증)였던 것을, 생성 호출이 Kafka 메시지로 바뀌면서 메시지 기준으로 옮겼다.
 * 기준 파일은 저장소 루트의 contracts/*.json이고, 워커 쪽 test_message_contract.py도 같은 파일을 읽는다.
 */
class GenerationMessageContractTest {
    private static final Path CONTRACTS = Path.of("..", "..", "contracts");
    private final ObjectMapper objectMapper = new ObjectMapper();

    private JsonNode contract(String name) throws IOException {
        return objectMapper.readTree(Files.readString(CONTRACTS.resolve(name)));
    }

    private static Set<String> fieldNames(JsonNode node) {
        Set<String> names = new HashSet<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }

    @Test
    void requestedMessageCarriesExactlyTheContractFields() throws IOException {
        ReportJob job = ReportJob.builder()
                .jobId(UUID.randomUUID()).userId("analyst").traceId("trace")
                .title("Q4 analysis").chapter("Financial results").indicator("revenue")
                .evaluations("Use only supplied evidence").company("Celltrion").date("2024 Q4")
                .build();

        JsonNode payload = objectMapper.valueToTree(ReportGenerationRequested.of(job, 1));

        assertThat(fieldNames(payload)).isEqualTo(fieldNames(contract("generation.requested.v1.json")));
        assertThat(payload.path("evaluations").asText()).isEqualTo("Use only supplied evidence");
        assertThat(payload.has("evaluation")).isFalse();
    }

    @Test
    void workerMessagesFromContractDeserializeIntoRecords() throws IOException {
        GenerationProgressed progressed = objectMapper.treeToValue(contract("generation.progressed.v1.json"), GenerationProgressed.class);
        GenerationCompleted completed = objectMapper.treeToValue(contract("generation.completed.v1.json"), GenerationCompleted.class);
        GenerationFailed failed = objectMapper.treeToValue(contract("generation.failed.v1.json"), GenerationFailed.class);

        assertThat(progressed.stage()).isEqualTo("SECTION_2");
        assertThat(completed.terms()).hasSize(1);
        assertThat(completed.terms().get(0).term()).isEqualTo("PER");
        assertThat(completed.generationTimeSeconds()).isEqualTo(42.5);
        assertThat(failed.retryable()).isTrue();
        assertThat(fieldNames(objectMapper.valueToTree(completed)))
                .isEqualTo(fieldNames(contract("generation.completed.v1.json")));
    }
}
