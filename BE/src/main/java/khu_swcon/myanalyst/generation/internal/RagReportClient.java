package khu_swcon.myanalyst.generation.internal;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import khu_swcon.myanalyst.report.ReportTerm;
import khu_swcon.myanalyst.shared.ApiException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * RAG 서버의 보고서 생성 API(FastAPI {@code /reports}) 클라이언트.
 */
@Component
public class RagReportClient {
    private static final Logger log = LoggerFactory.getLogger(RagReportClient.class);

    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    public RagReportClient(WebClient ragWebClient, ObjectMapper objectMapper) {
        this.webClient = ragWebClient;
        this.objectMapper = objectMapper;
    }

    public GeneratedContent generate(ReportJob job) {
        // API 요청 데이터 설정
        Map<String, String> requestBody = new HashMap<>();
        requestBody.put("title", job.getTitle());
        requestBody.put("company", job.getCompany());
        requestBody.put("date", job.getDate());
        requestBody.put("chapter", job.getChapter());
        requestBody.put("indicator", job.getIndicator());
        requestBody.put("evaluations", job.getEvaluations() == null ? "" : job.getEvaluations());
        requestBody.put("generation_job_id", job.getJobId().toString());

        Map<String, Object> response;
        try {
            response = webClient.post()
                    .uri("/reports")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(Map.class)
                    .block(); // 동기적으로 응답 대기
        } catch (Exception e) {
            throw new ApiException("리포트 생성 API 호출 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }

        if (response == null || !response.containsKey("report")) {
            throw new ApiException("리포트 생성 API 호출 결과가 유효하지 않습니다.", HttpStatus.INTERNAL_SERVER_ERROR);
        }
        return new GeneratedContent(response.get("report").toString(), terms(response.get("domain_specific_terms")));
    }

    private List<ReportTerm> terms(Object raw) {
        if (!(raw instanceof List)) {
            return List.of();
        }
        try {
            return objectMapper.convertValue(raw, new TypeReference<List<ReportTerm>>() {});
        } catch (IllegalArgumentException e) {
            // 용어 추출 실패가 보고서 생성 전체를 실패시키지 않도록 비워 둔다.
            log.warn("도메인 용어 응답을 해석하지 못했습니다: {}", e.getMessage());
            return List.of();
        }
    }

    public record GeneratedContent(String report, List<ReportTerm> terms) {
    }
}
