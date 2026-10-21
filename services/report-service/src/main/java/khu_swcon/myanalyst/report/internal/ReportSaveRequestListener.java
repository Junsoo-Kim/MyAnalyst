package khu_swcon.myanalyst.report.internal;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import khu_swcon.myanalyst.report.GeneratedReport;
import khu_swcon.myanalyst.report.ReportService;
import khu_swcon.myanalyst.report.ReportTerm;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.UUID;

/**
 * generation-service의 저장 명령({@value #TOPIC})을 받아 보고서를 저장한다(Saga의 저장 단계). 저장과
 * {@code ReportCreated} 발행은 한 트랜잭션이고(Outbox), 그 이벤트가 generation-service에 완료를 알린다.
 * 같은 명령이 다시 와도 generationJobId로 이미 저장된 보고서를 찾아 아무것도 하지 않는다(멱등).
 * 계약: {@code contracts/report.save-requested.v1.json}.
 */
@Component
public class ReportSaveRequestListener {
    static final String TOPIC = "report.save-requested";

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ReportSaveRequested(UUID jobId, String userId, String title, String chapter, String indicator,
                                      String company, String date, String content, List<ReportTerm> terms) {
    }

    private final ReportService reportService;

    public ReportSaveRequestListener(ReportService reportService) {
        this.reportService = reportService;
    }

    @KafkaListener(topics = TOPIC, groupId = "report")
    public void on(ReportSaveRequested command) {
        reportService.saveGeneratedReport(new GeneratedReport(command.jobId(), command.userId(), command.title(),
                command.chapter(), command.indicator(), command.company(), command.date(), command.content(),
                command.terms() == null ? List.of() : command.terms()));
    }
}
