package khu_swcon.myanalyst.dictionary;

import com.fasterxml.jackson.databind.ObjectMapper;
import khu_swcon.myanalyst.dictionary.events.ReportCreated;
import khu_swcon.myanalyst.dictionary.events.ReportDeleted;
import khu_swcon.myanalyst.dictionary.events.ReportEvents;
import khu_swcon.myanalyst.dictionary.events.ReportTerm;
import khu_swcon.myanalyst.dictionary.internal.Dictionary;
import khu_swcon.myanalyst.dictionary.internal.DictionaryReport;
import khu_swcon.myanalyst.dictionary.internal.DictionaryReportRepository;
import khu_swcon.myanalyst.dictionary.internal.DictionaryRepository;
import khu_swcon.myanalyst.shared.ApiException;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class DictionaryService {
    private static final Logger log = LoggerFactory.getLogger(DictionaryService.class);

    private final DictionaryRepository dictionaryRepository;
    private final DictionaryReportRepository reportRepository;
    private final ObjectMapper objectMapper;

    public DictionaryService(DictionaryRepository dictionaryRepository, DictionaryReportRepository reportRepository,
                             ObjectMapper objectMapper) {
        this.dictionaryRepository = dictionaryRepository;
        this.reportRepository = reportRepository;
        this.objectMapper = objectMapper;
    }

    /**
     * 리포트 ID로 사전 용어 목록을 조회. 소유권은 보고서 서비스에 묻지 않고 {@code report.created}로 받아 둔
     * 사본(dictionary_reports)으로 판단한다. 사본이 아직 없으면(이벤트 도착 전이거나 삭제된 보고서) 404다.
     *
     * @param reportId 리포트 ID
     * @return 도메인 특화 용어 목록
     */
    @Transactional(readOnly = true)
    public List<DomainSpecificTermDto> getDictionaryByReportId(Integer reportId, String userId) {
        DictionaryReport report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException("Report not found with ID: " + reportId, HttpStatus.NOT_FOUND));
        if (!report.getUserId().equals(userId)) {
            throw new ApiException("You do not have access to this report", HttpStatus.FORBIDDEN);
        }

        return dictionaryRepository.findByReportId(reportId).stream()
                .map(dictionary -> DomainSpecificTermDto.builder()
                        .term(dictionary.getWord())
                        .explanation(dictionary.getDetail())
                        .build())
                .collect(Collectors.toList());
    }

    /**
     * Kafka {@code report.created}를 소비한다. 이 토픽에는 생성(ReportCreated)과 삭제(ReportDeleted)가 같은 key로
     * 함께 오고 {@code event-type} 헤더로 구분한다. 메시지는 최소 한 번 이상 올 수 있으므로 둘 다 멱등이다.
     * 실패하면 재시도 후 {@code report.created.DLT}로 간다.
     */
    @KafkaListener(topics = ReportEvents.TOPIC, groupId = "dictionary")
    @Transactional
    public void on(ConsumerRecord<String, byte[]> record) throws IOException {
        String eventType = ReportEvents.eventType(record);
        switch (eventType) {
            case ReportEvents.CREATED -> onCreated(objectMapper.readValue(record.value(), ReportCreated.class));
            case ReportEvents.DELETED -> onDeleted(objectMapper.readValue(record.value(), ReportDeleted.class));
            default -> log.warn("알 수 없는 이벤트 타입 무시: {} (offset={})", eventType, record.offset());
        }
    }

    private void onCreated(ReportCreated event) {
        reportRepository.save(new DictionaryReport(event.reportId(), event.userId()));
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

    private void onDeleted(ReportDeleted event) {
        dictionaryRepository.deleteByReportId(event.reportId());
        reportRepository.deleteById(event.reportId());
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
