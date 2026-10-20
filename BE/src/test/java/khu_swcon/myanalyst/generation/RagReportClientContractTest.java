package khu_swcon.myanalyst.generation;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import khu_swcon.myanalyst.generation.internal.RagReportClient;
import khu_swcon.myanalyst.generation.internal.ReportJob;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Spring → FastAPI 보고서 생성 계약. 원래 ReportServiceContractTest에 있던 검증으로,
 * RAG 호출이 생성 모듈로 옮겨지면서 함께 옮겼다.
 */
class RagReportClientContractTest {
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final AtomicReference<String> receivedBody = new AtomicReference<>();
    private HttpServer ragServer;

    @BeforeEach
    void startRagStub() throws Exception {
        ragServer = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        ragServer.createContext("/reports", exchange -> {
            receivedBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] response = "{\"report\":\"generated report\",\"generation_time_seconds\":1.0,\"domain_specific_terms\":[]}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(201, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        ragServer.start();
    }

    @AfterEach
    void stopRagStub() {
        ragServer.stop(0);
    }

    @Test
    void sendsPluralEvaluationsFieldRequiredByFastApiSchema() throws Exception {
        WebClient client = WebClient.builder()
                .baseUrl("http://localhost:" + ragServer.getAddress().getPort())
                .build();
        RagReportClient ragReportClient = new RagReportClient(client, objectMapper);

        RagReportClient.GeneratedContent generated = ragReportClient.generate(ReportJob.builder()
                .jobId(UUID.randomUUID())
                .userId("analyst")
                .title("Q4 analysis")
                .chapter("Financial results")
                .indicator("revenue")
                .evaluations("Use only supplied evidence")
                .company("Celltrion")
                .date("2024 Q4")
                .build());

        JsonNode payload = objectMapper.readTree(receivedBody.get());
        assertThat(payload.path("evaluations").asText()).isEqualTo("Use only supplied evidence");
        assertThat(payload.has("evaluation")).isFalse();
        assertThat(generated.report()).isEqualTo("generated report");
    }
}
