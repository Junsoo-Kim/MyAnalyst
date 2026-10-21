package khu_swcon.myanalyst.report;

import khu_swcon.myanalyst.report.internal.Report;
import khu_swcon.myanalyst.report.internal.ReportRepository;
import khu_swcon.myanalyst.shared.ApiException;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * 보고서 저장·조회·삭제. 다른 서비스(generation, dictionary, chat)는 이 클래스를 부르지 않고
 * {@link ReportCreated}, {@link ReportDeleted} 이벤트로 결과를 알게 된다.
 */
@Service
public class ReportService {

    private final ReportRepository reportRepository;
    private final ApplicationEventPublisher events;

    public ReportService(ReportRepository reportRepository, ApplicationEventPublisher events) {
        this.reportRepository = reportRepository;
        this.events = events;
    }

    /**
     * 생성 결과를 저장한다. 같은 생성 Job으로 다시 호출되면 기존 보고서 ID를 돌려준다.
     */
    @Transactional
    public Integer saveGeneratedReport(GeneratedReport generated) {
        return reportRepository.findByGenerationJobId(generated.generationJobId())
                .map(Report::getReportid)
                .orElseGet(() -> {
                    Report saved = reportRepository.save(Report.builder()
                            .userId(generated.userId())
                            .title(generated.title())
                            .chapter(generated.chapter())
                            .content(generated.content())
                            .indicator(generated.indicator())
                            .company(generated.company())
                            .date(generated.date())
                            .generationJobId(generated.generationJobId())
                            .build());
                    events.publishEvent(new ReportCreated(
                            saved.getReportid(), saved.getGenerationJobId(), saved.getUserId(),
                            saved.getContent(), generated.terms()));
                    return saved.getReportid();
                });
    }

    @Transactional(readOnly = true)
    public Optional<Integer> findReportIdByGenerationJobId(UUID generationJobId) {
        return reportRepository.findByGenerationJobId(generationJobId).map(Report::getReportid);
    }

    @Transactional(readOnly = true)
    public List<ReportListDto> getReportsOf(String userId) {
        return reportRepository.findByUserId(userId).stream()
                .map(report -> ReportListDto.builder()
                        .reportid(report.getReportid())
                        .title(report.getTitle())
                        .build())
                .collect(Collectors.toList());
    }

    @Transactional(readOnly = true)
    public ReportDetailDto getReportById(Integer reportId, String userId) {
        Report report = findOwnedReport(reportId, userId);

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
    public void deleteReport(Integer reportId, String userId) {
        Report report = findOwnedReport(reportId, userId);
        reportRepository.delete(report);
        events.publishEvent(new ReportDeleted(reportId));
    }

    private Report findOwnedReport(Integer reportId, String userId) {
        Report report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException("Report not found with ID: " + reportId, HttpStatus.NOT_FOUND));
        if (!report.getUserId().equals(userId)) {
            throw new ApiException("You do not have access to this report", HttpStatus.FORBIDDEN);
        }
        return report;
    }
}
