package khu_swcon.myanalyst.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import khu_swcon.myanalyst.dto.ReportDto;
import khu_swcon.myanalyst.entity.Report;
import khu_swcon.myanalyst.entity.User;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.repository.DictionaryRepository;
import khu_swcon.myanalyst.repository.ReportRepository;
import khu_swcon.myanalyst.repository.UserRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ReportServiceContractTest {
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
        UserRepository users = mock(UserRepository.class);
        ReportRepository reports = mock(ReportRepository.class);
        DictionaryRepository dictionaries = mock(DictionaryRepository.class);
        User user = User.builder().userid("analyst").password("hashed").build();
        when(users.findByUserid("analyst")).thenReturn(Optional.of(user));
        when(reports.save(any(Report.class))).thenAnswer(invocation -> invocation.getArgument(0));

        WebClient client = WebClient.builder()
                .baseUrl("http://localhost:" + ragServer.getAddress().getPort())
                .build();
        ReportService service = new ReportService(reports, users, dictionaries, client, objectMapper);

        service.createReport(ReportDto.builder()
                .userid("analyst")
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
        verify(reports).save(any(Report.class));
    }

    @Test
    void rejectsAccessToAnotherUsersReport() {
        UserRepository users = mock(UserRepository.class);
        ReportRepository reports = mock(ReportRepository.class);
        DictionaryRepository dictionaries = mock(DictionaryRepository.class);
        User owner = User.builder().userid("owner").password("hashed").build();
        Report report = Report.builder()
                .reportid(41)
                .user(owner)
                .title("Private report")
                .content("Confidential")
                .build();
        when(reports.findById(41)).thenReturn(Optional.of(report));

        ReportService service = new ReportService(reports, users, dictionaries,
                WebClient.builder().baseUrl("http://localhost").build(), objectMapper);

        assertThatThrownBy(() -> service.getReportById(41, "intruder"))
                .isInstanceOf(ApiException.class)
                .hasMessageContaining("do not have access");
    }
}
