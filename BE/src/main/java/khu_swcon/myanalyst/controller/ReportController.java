package khu_swcon.myanalyst.controller;

import khu_swcon.myanalyst.dto.ReportDetailDto;
import khu_swcon.myanalyst.dto.ReportDto;
import khu_swcon.myanalyst.dto.ReportListDto;
import khu_swcon.myanalyst.dto.NewsDto;
import khu_swcon.myanalyst.dto.StockDto;
import khu_swcon.myanalyst.dto.DomainSpecificTermDto;
import khu_swcon.myanalyst.dto.ChatHistoryDto;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.exception.UserNotFoundException;
import khu_swcon.myanalyst.service.ReportService;
import khu_swcon.myanalyst.service.DictionaryService;
import khu_swcon.myanalyst.service.ChatService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.core.io.ByteArrayResource;
import jakarta.servlet.http.HttpSession;

import java.util.List;

@RestController
public class ReportController {
    
    private final ReportService reportService;
    private final DictionaryService dictionaryService;
    private final ChatService chatService;
    
    @Autowired
    public ReportController(ReportService reportService, 
                            DictionaryService dictionaryService,
                            ChatService chatService) {
        this.reportService = reportService;
        this.dictionaryService = dictionaryService;
        this.chatService = chatService;
    }
    
    @PostMapping("/reports")
    public ResponseEntity<?> createReport(@RequestBody ReportDto reportDto, HttpSession session) {
        try {
            reportDto.setUserid(currentUser(session));
            reportService.createReport(reportDto);
            return new ResponseEntity<>("", HttpStatus.OK);
        } catch (UserNotFoundException e) {
            return new ResponseEntity<>(e.getMessage(), HttpStatus.NOT_FOUND);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("Report 생성 중 오류가 발생했습니다: " + e.getMessage(), 
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    @GetMapping("/reports")
    public ResponseEntity<?> getAllReports(HttpSession session) {
        try {
            List<ReportListDto> reports = reportService.getAllReports(currentUser(session));
            return new ResponseEntity<>(reports, HttpStatus.OK);
        } catch (Exception e) {
            return new ResponseEntity<>("Report 목록 조회 중 오류가 발생했습니다: " + e.getMessage(), 
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    @GetMapping("/reports/{reportId}")
    public ResponseEntity<?> getReportById(@PathVariable Integer reportId, HttpSession session) {
        try {
            ReportDetailDto reportDetail = reportService.getReportById(reportId, currentUser(session));
            return new ResponseEntity<>(reportDetail, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("Report 상세 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    @GetMapping("/reports/user/{userId}")
    public ResponseEntity<?> getReportsByUserId(@PathVariable String userId, HttpSession session) {
        try {
            if (!currentUser(session).equals(userId)) {
                return new ResponseEntity<>("You do not have access to these reports", HttpStatus.FORBIDDEN);
            }
            List<ReportListDto> reports = reportService.getReportsByUserId(userId);
            return new ResponseEntity<>(reports, HttpStatus.OK);
        } catch (UserNotFoundException e) {
            return new ResponseEntity<>(e.getMessage(), HttpStatus.NOT_FOUND);
        } catch (Exception e) {
            return new ResponseEntity<>("사용자의 Report 목록 조회 중 오류가 발생했습니다: " + e.getMessage(), 
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    @DeleteMapping("/reports/{reportId}")
    public ResponseEntity<?> deleteReport(@PathVariable Integer reportId, HttpSession session) {
        try {
            reportService.deleteReport(reportId, currentUser(session));
            return new ResponseEntity<>(HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("Report 삭제 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
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
            List<NewsDto> news = reportService.getNewsByCompany(company);
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
            StockDto stock = reportService.getStockByCompany(company);
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
            return reportService.getStockChartImage(company);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("차트 이미지 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    /**
     * 리포트 ID로 사전 용어 목록 조회
     * 
     * @param reportId 리포트 ID
     * @return 도메인 특화 용어 목록
     */
    @GetMapping("/reports/{reportId}/dictionary")
    public ResponseEntity<?> getDictionaryByReportId(@PathVariable Integer reportId, HttpSession session) {
        try {
            List<DomainSpecificTermDto> terms = dictionaryService.getDictionaryByReportId(reportId, currentUser(session));
            return new ResponseEntity<>(terms, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("사전 용어 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    /**
     * 리포트 ID로 채팅 기록 조회
     * 
     * @param reportId 리포트 ID
     * @return 채팅 기록 목록
     */
    @GetMapping("/reports/{reportId}/chat")
    public ResponseEntity<?> getChatHistoryByReportId(@PathVariable Integer reportId, HttpSession session) {
        try {
            List<ChatHistoryDto> chats = chatService.getChatHistoryByReportId(reportId, currentUser(session));
            return new ResponseEntity<>(chats, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("채팅 기록 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    private String currentUser(HttpSession session) {
        return (String) session.getAttribute("userId");
    }
}
