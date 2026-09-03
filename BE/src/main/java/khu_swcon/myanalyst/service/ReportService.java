package khu_swcon.myanalyst.service;

import khu_swcon.myanalyst.dto.NewsDto;
import khu_swcon.myanalyst.dto.ReportDetailDto;
import khu_swcon.myanalyst.dto.ReportDto;
import khu_swcon.myanalyst.dto.ReportListDto;
import khu_swcon.myanalyst.dto.StockDto;
import khu_swcon.myanalyst.dto.DomainSpecificTermDto;
import khu_swcon.myanalyst.entity.Report;
import khu_swcon.myanalyst.entity.User;
import khu_swcon.myanalyst.entity.Dictionary;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.exception.UserNotFoundException;
import khu_swcon.myanalyst.repository.ReportRepository;
import khu_swcon.myanalyst.repository.UserRepository;
import khu_swcon.myanalyst.repository.DictionaryRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.reactive.function.client.WebClient;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class ReportService {
    
    private final ReportRepository reportRepository;
    private final UserRepository userRepository;
    private final DictionaryRepository dictionaryRepository;
    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    // RAG(FastAPI) 서버 주소. 로컬은 localhost:8000, 컨테이너/클라우드에서는
    // RAG_SERVER_BASE_URL 환경 변수로 서비스 디스커버리 이름을 주입합니다.
    @Value("${rag.server.base-url}")
    private String ragServerBaseUrl;

    @Autowired
    public ReportService(ReportRepository reportRepository,
                        UserRepository userRepository, 
                        DictionaryRepository dictionaryRepository) {
        this.reportRepository = reportRepository;
        this.userRepository = userRepository;
        this.dictionaryRepository = dictionaryRepository;
        this.webClient = WebClient.create();
        this.objectMapper = new ObjectMapper();
    }
    
    @Transactional
    public Report createReport(ReportDto reportDto) {
        // 1. 사용자 ID 검증
        User user = userRepository.findByUserid(reportDto.getUserid())
                .orElseThrow(() -> new UserNotFoundException("사용자 ID가 존재하지 않습니다: " + reportDto.getUserid()));
        
        // company와 date에 기본값 설정
        String company = reportDto.getCompany() != null && !reportDto.getCompany().isEmpty() ? 
                         reportDto.getCompany() : "셀트리온";
        String date = reportDto.getDate() != null && !reportDto.getDate().isEmpty() ? 
                      reportDto.getDate() : "24년 4분기";
        
        // 2. Report 객체 생성 (company와 date 추가)
        Report report = Report.builder()
                .user(user)
                .title(reportDto.getTitle())
                .chapter(reportDto.getChapter())
                .content("") // 임시로 빈 문자열 설정, API 응답 후 업데이트 예정
                .indicator(reportDto.getIndicator())
                .company(company)
                .date(date)
                .build();
        
        // 3. 외부 API 호출하여 리포트 내용 생성 및 도메인 용어 저장
        Map<String, Object> apiResponse = generateReportAndTerms(report, reportDto.getEvaluations(), 
                                                  company, date);
        
        // 리포트 내용 설정
        if (apiResponse.containsKey("report")) {
            report.setContent(apiResponse.get("report").toString());
        } else {
            throw new ApiException("리포트 생성 API 호출 결과가 유효하지 않습니다.", HttpStatus.INTERNAL_SERVER_ERROR);
        }
        
        // 4. DB에 저장
        Report savedReport = reportRepository.save(report);
        
        // 5. 도메인 특화 용어 저장 (saved Report 사용)
        if (apiResponse.containsKey("domain_specific_terms")) {
            saveDomainSpecificTerms(savedReport, apiResponse.get("domain_specific_terms"));
        }
        
        return savedReport;
    }
    
    /**
     * 외부 API를 호출하여 리포트 내용과 도메인 용어를 생성
     * 
     * @param report 생성할 리포트 정보
     * @param evaluations 평가 기준
     * @param company 회사명
     * @param date 날짜
     * @return API 응답
     */
    private Map<String, Object> generateReportAndTerms(Report report, String evaluations, String company, String date) {
        // API 요청 데이터 설정
        Map<String, String> requestBody = new HashMap<>();
        requestBody.put("title", report.getTitle());
        requestBody.put("company", company);
        requestBody.put("date", date);
        requestBody.put("chapter", report.getChapter());
        requestBody.put("indicator", report.getIndicator());
        
        // localhost:8000에서 'evaluation'으로 필드명을 기대하고 있다면 아래와 같이 변경
        requestBody.put("evaluation", evaluations);  // 'evaluations' 대신 'evaluation'으로 변경
        
        // API 호출 및 응답 처리
        try {
            Map<String, Object> response = webClient.post()
                    .uri(ragServerBaseUrl + "/reports")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(Map.class)
                    .block(); // 동기적으로 응답 대기
            
            return response != null ? response : new HashMap<>();
        } catch (Exception e) {
            throw new ApiException("리포트 생성 API 호출 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    /**
     * 도메인 특화 용어 저장
     * 
     * @param report 저장된 리포트
     * @param domainTermsObject API 응답에서 추출한 도메인 용어 객체
     */
    private void saveDomainSpecificTerms(Report report, Object domainTermsObject) {
        try {
            List<DomainSpecificTermDto> terms;
            
            // Object를 List<DomainSpecificTermDto>로 변환
            if (domainTermsObject instanceof List) {
                terms = objectMapper.convertValue(domainTermsObject, 
                        new TypeReference<List<DomainSpecificTermDto>>() {});
            } else {
                return; // 변환할 수 없는 경우 종료
            }
            
            // Dictionary 엔티티로 변환하여 저장
            List<Dictionary> dictionaries = new ArrayList<>();
            for (DomainSpecificTermDto term : terms) {
                Dictionary dictionary = Dictionary.builder()
                        .report(report)
                        .word(term.getTerm())
                        .detail(term.getExplanation())
                        .build();
                
                dictionaries.add(dictionary);
            }
            
            // 한번에 저장
            dictionaryRepository.saveAll(dictionaries);
            
        } catch (Exception e) {
            // 용어 저장 실패는 전체 프로세스를 중단시키지 않고 로그만 남김
            System.err.println("도메인 용어 저장 중 오류 발생: " + e.getMessage());
        }
    }
    
    @Transactional(readOnly = true)
    public List<ReportListDto> getAllReports() {
        List<Report> reports = reportRepository.findAll();
        
        // Convert Report entities to ReportListDto objects
        return reports.stream()
                .map(report -> ReportListDto.builder()
                        .reportid(report.getReportid())
                        .title(report.getTitle())
                        .build())
                .collect(Collectors.toList());
    }
    
    @Transactional(readOnly = true)
    public ReportDetailDto getReportById(Integer reportId) {
        Report report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException("Report not found with ID: " + reportId, HttpStatus.NOT_FOUND));
        
        return ReportDetailDto.builder()
                .title(report.getTitle())
                .chapter(report.getChapter())
                .content(report.getContent())
                .company(report.getCompany())
                .date(report.getDate())
                .indicator(report.getIndicator())
                .build();
    }
    
    @Transactional
    public void deleteReport(Integer reportId) {
        // Check if report exists
        Report report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException("Report not found with ID: " + reportId, HttpStatus.NOT_FOUND));
        
        // Delete the report
        reportRepository.delete(report);
    }
    
    @Transactional(readOnly = true)
    public List<ReportListDto> getReportsByUserId(String userId) {
        // 1. 사용자 ID 검증
        User user = userRepository.findByUserid(userId)
                .orElseThrow(() -> new UserNotFoundException("사용자 ID가 존재하지 않습니다: " + userId));
        
        // 2. 해당 사용자의 리포트 목록 조회
        List<Report> reports = reportRepository.findByUser(user);
        
        // 3. Convert Report entities to ReportListDto objects
        return reports.stream()
                .map(report -> ReportListDto.builder()
                        .reportid(report.getReportid())
                        .title(report.getTitle())
                        .build())
                .collect(Collectors.toList());
    }
    
    /**
     * 회사명으로 뉴스 정보를 조회
     * 
     * @param company 회사명
     * @return 뉴스 정보 목록
     */
    // 같은 회사에 대한 반복 요청은 RAG 서버(->네이버 크롤링)를 다시 타지 않고 Redis 캐시에서 응답한다.
    @Cacheable(cacheNames = "news", key = "#company")
    @Transactional(readOnly = true)
    public List<NewsDto> getNewsByCompany(String company) {
        try {
            // API 호출 및 응답 처리
            return webClient.get()
                    .uri(ragServerBaseUrl + "/news/{company}", company)
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
    // 주가는 뉴스보다 실시간성이 중요하므로 캐시 TTL을 짧게(1분) 잡아둔다 (RedisCacheConfig 참고).
    @Cacheable(cacheNames = "stocks", key = "#company")
    @Transactional(readOnly = true)
    public StockDto getStockByCompany(String company) {
        try {
            // API 호출 및 응답 처리
            return webClient.get()
                    .uri(ragServerBaseUrl + "/stocks/{company}", company)
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
                    .uri(ragServerBaseUrl + "/stocks/{company}/chart-image", company)
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
