package khu_swcon.myanalyst.marketdata.web;

import khu_swcon.myanalyst.marketdata.MarketDataService;
import khu_swcon.myanalyst.marketdata.NewsDto;
import khu_swcon.myanalyst.marketdata.StockDto;
import khu_swcon.myanalyst.shared.ApiException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
public class MarketDataController {

    private final MarketDataService marketDataService;

    public MarketDataController(MarketDataService marketDataService) {
        this.marketDataService = marketDataService;
    }

    /**
     * 회사명으로 뉴스 정보를 조회
     *
     * @param company 회사명
     * @return 뉴스 정보 목록
     */
    @GetMapping("/news/{company}")
    public ResponseEntity<?> getNewsByCompany(@PathVariable String company) {
        try {
            List<NewsDto> news = marketDataService.getNewsByCompany(company);
            return new ResponseEntity<>(news, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("뉴스 정보 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 회사명으로 주식 정보를 조회
     *
     * @param company 회사명
     * @return 주식 정보
     */
    @GetMapping("/stocks/{company}")
    public ResponseEntity<?> getStockByCompany(@PathVariable String company) {
        try {
            StockDto stock = marketDataService.getStockByCompany(company);
            return new ResponseEntity<>(stock, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("주식 정보 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 회사명으로 주식 차트 이미지를 조회
     *
     * @param company 회사명
     * @return 차트 이미지
     */
    @GetMapping("/stocks/{company}/chart-image")
    public ResponseEntity<?> getStockChartImage(@PathVariable String company) {
        try {
            return marketDataService.getStockChartImage(company);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("차트 이미지 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}
