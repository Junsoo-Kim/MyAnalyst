package khu_swcon.myanalyst.marketdata;

import khu_swcon.myanalyst.shared.ApiException;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.List;

/**
 * 뉴스·주가·차트 조회. 보고서와 무관하게 RAG 서버의 크롤링 API를 중계하고 Redis에 캐시한다.
 */
@Service
public class MarketDataService {

    private final WebClient webClient;

    public MarketDataService(WebClient ragWebClient) {
        this.webClient = ragWebClient;
    }

    /**
     * 회사명으로 뉴스 정보를 조회
     *
     * @param company 회사명
     * @return 뉴스 정보 목록
     */
    @Cacheable(cacheNames = "news", key = "#company")
    public List<NewsDto> getNewsByCompany(String company) {
        try {
            // API 호출 및 응답 처리
            return webClient.get()
                    .uri("/news/{company}", company)
                    .retrieve()
                    .bodyToFlux(NewsDto.class)
                    .collectList()
                    .block(); // 동기적으로 응답 대기
        } catch (Exception e) {
            throw new ApiException("뉴스 정보 조회 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 회사명으로 주식 정보를 조회
     *
     * @param company 회사명
     * @return 주식 정보
     */
    @Cacheable(cacheNames = "stocks", key = "#company")
    public StockDto getStockByCompany(String company) {
        try {
            // API 호출 및 응답 처리
            return webClient.get()
                    .uri("/stocks/{company}", company)
                    .retrieve()
                    .bodyToMono(StockDto.class)
                    .block(); // 동기적으로 응답 대기
        } catch (Exception e) {
            throw new ApiException("주식 정보 조회 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 회사명으로 주식 차트 이미지를 조회
     *
     * @param company 회사명
     * @return 차트 이미지 바이트 배열
     */
    public ResponseEntity<ByteArrayResource> getStockChartImage(String company) {
        try {
            // API 호출 및 응답 처리
            byte[] imageBytes = webClient.get()
                    .uri("/stocks/{company}/chart-image", company)
                    .accept(MediaType.IMAGE_PNG, MediaType.IMAGE_JPEG, MediaType.APPLICATION_OCTET_STREAM)
                    .retrieve()
                    .bodyToMono(byte[].class)
                    .block(); // 동기적으로 응답 대기

            if (imageBytes == null || imageBytes.length == 0) {
                throw new ApiException("차트 이미지를 가져올 수 없습니다.", HttpStatus.NOT_FOUND);
            }

            ByteArrayResource resource = new ByteArrayResource(imageBytes);

            // 이미지 데이터와 함께 적절한 헤더 설정
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.IMAGE_PNG); // 기본값으로 PNG 설정
            headers.setContentLength(imageBytes.length);

            return ResponseEntity.ok()
                    .headers(headers)
                    .body(resource);

        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException("차트 이미지 조회 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}
