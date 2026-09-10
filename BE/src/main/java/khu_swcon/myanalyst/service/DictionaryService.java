package khu_swcon.myanalyst.service;

import khu_swcon.myanalyst.dto.DomainSpecificTermDto;
import khu_swcon.myanalyst.entity.Dictionary;
import khu_swcon.myanalyst.entity.Report;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.repository.DictionaryRepository;
import khu_swcon.myanalyst.repository.ReportRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class DictionaryService {
    
    private final DictionaryRepository dictionaryRepository;
    private final ReportRepository reportRepository;
    
    @Autowired
    public DictionaryService(DictionaryRepository dictionaryRepository, ReportRepository reportRepository) {
        this.dictionaryRepository = dictionaryRepository;
        this.reportRepository = reportRepository;
    }
    
    /**
     * 리포트 ID로 사전 용어 목록을 조회
     * 
     * @param reportId 리포트 ID
     * @return 도메인 특화 용어 목록
     */
    @Transactional(readOnly = true)
    public List<DomainSpecificTermDto> getDictionaryByReportId(Integer reportId, String userId) {
        // 리포트 존재 여부 확인
        Report report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException("Report not found with ID: " + reportId, HttpStatus.NOT_FOUND));
        if (!report.getUser().getUserid().equals(userId)) {
            throw new ApiException("You do not have access to this report", HttpStatus.FORBIDDEN);
        }
        
        // 해당 리포트의 사전 용어 조회
        List<Dictionary> dictionaries = dictionaryRepository.findByReport(report);
        
        // Dictionary 엔티티를 DomainSpecificTermDto로 변환
        return dictionaries.stream()
                .map(dictionary -> DomainSpecificTermDto.builder()
                        .term(dictionary.getWord())
                        .explanation(dictionary.getDetail())
                        .build())
                .collect(Collectors.toList());
    }
}
