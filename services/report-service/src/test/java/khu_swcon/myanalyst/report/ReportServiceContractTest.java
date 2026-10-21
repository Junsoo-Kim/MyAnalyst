package khu_swcon.myanalyst.report;

import khu_swcon.myanalyst.report.internal.Report;
import khu_swcon.myanalyst.report.internal.ReportRepository;
import khu_swcon.myanalyst.shared.ApiException;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

class ReportServiceContractTest {

    @Test
    void rejectsAccessToAnotherUsersReport() {
        ReportRepository reports = mock(ReportRepository.class);
        Report report = Report.builder()
                .reportid(41)
                .userId("owner")
                .title("Private report")
                .content("Confidential")
                .build();
        when(reports.findById(41)).thenReturn(Optional.of(report));

        ReportService service = new ReportService(reports, mock(ApplicationEventPublisher.class));

        assertThatThrownBy(() -> service.getReportById(41, "intruder"))
                .isInstanceOf(ApiException.class)
                .hasMessageContaining("do not have access");
    }
}
