package khu_swcon.myanalyst.dictionary;

import khu_swcon.myanalyst.dictionary.internal.Dictionary;
import khu_swcon.myanalyst.dictionary.internal.DictionaryRepository;
import khu_swcon.myanalyst.report.ReportCreated;
import khu_swcon.myanalyst.report.ReportDeleted;
import khu_swcon.myanalyst.report.ReportService;
import khu_swcon.myanalyst.report.ReportTerm;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class DictionaryService {
    private static final Logger log = LoggerFactory.getLogger(DictionaryService.class);

    private final DictionaryRepository dictionaryRepository;
    private final ReportService reportService;

    public DictionaryService(DictionaryRepository dictionaryRepository, ReportService reportService) {
        this.dictionaryRepository = dictionaryRepository;
        this.reportService = reportService;
    }

    /**
     * 리포트 ID로 사전 용어 목록을 조회
     *
     * @param reportId 리포트 ID
     * @return 도메인 특화 용어 목록
     */
    @Transactional(readOnly = true)
    public List<DomainSpecificTermDto> getDictionaryByReportId(Integer reportId, String userId) {
        reportService.assertOwnedBy(reportId, userId);

        return dictionaryRepository.findByReportId(reportId).stream()
                .map(dictionary -> DomainSpecificTermDto.builder()
                        .term(dictionary.getWord())
                        .explanation(dictionary.getDetail())
                        .build())
                .collect(Collectors.toList());
    }

    /**
     * 보고서가 커밋된 뒤 별도 트랜잭션에서 용어를 저장한다. 실패하면 Modulith 이벤트 레지스트리에
     * 미완료로 남아 재전달되므로, 이미 저장된 보고서는 다시 저장하지 않는다.
     */
    @ApplicationModuleListener
    public void on(ReportCreated event) {
        if (event.terms() == null || dictionaryRepository.existsByReportId(event.reportId())) {
            return;
        }
        List<Dictionary> entries = event.terms().stream()
                .filter(this::fitsColumn)
                .map(term -> Dictionary.builder()
                        .reportId(event.reportId())
                        .word(term.term())
                        .detail(term.explanation())
                        .build())
                .collect(Collectors.toList());
        dictionaryRepository.saveAll(entries);
    }

    @ApplicationModuleListener
    public void on(ReportDeleted event) {
        dictionaryRepository.deleteByReportId(event.reportId());
    }

    private boolean fitsColumn(ReportTerm term) {
        boolean fits = term.term() != null && !term.term().isBlank()
                && term.term().length() <= Dictionary.MAX_WORD_LENGTH;
        if (!fits) {
            log.warn("용어 사전 저장 생략 (비어 있거나 {}자 초과): {}", Dictionary.MAX_WORD_LENGTH, term.term());
        }
        return fits;
    }
}
