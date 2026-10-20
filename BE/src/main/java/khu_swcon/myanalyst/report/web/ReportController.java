package khu_swcon.myanalyst.report.web;

import khu_swcon.myanalyst.auth.CurrentUser;
import khu_swcon.myanalyst.report.ReportDetailDto;
import khu_swcon.myanalyst.report.ReportListDto;
import khu_swcon.myanalyst.report.ReportService;
import khu_swcon.myanalyst.shared.ApiException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import jakarta.servlet.http.HttpServletRequest;

import java.util.List;

@RestController
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/reports")
    public ResponseEntity<?> getAllReports(HttpServletRequest request) {
        try {
            List<ReportListDto> reports = reportService.getReportsOf(CurrentUser.of(request));
            return new ResponseEntity<>(reports, HttpStatus.OK);
        } catch (Exception e) {
            return new ResponseEntity<>("Report 목록 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @GetMapping("/reports/{reportId}")
    public ResponseEntity<?> getReportById(@PathVariable Integer reportId, HttpServletRequest request) {
        try {
            ReportDetailDto reportDetail = reportService.getReportById(reportId, CurrentUser.of(request));
            return new ResponseEntity<>(reportDetail, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("Report 상세 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @GetMapping("/reports/user/{userId}")
    public ResponseEntity<?> getReportsByUserId(@PathVariable String userId, HttpServletRequest request) {
        try {
            if (!CurrentUser.of(request).equals(userId)) {
                return new ResponseEntity<>("You do not have access to these reports", HttpStatus.FORBIDDEN);
            }
            List<ReportListDto> reports = reportService.getReportsOf(userId);
            return new ResponseEntity<>(reports, HttpStatus.OK);
        } catch (Exception e) {
            return new ResponseEntity<>("사용자의 Report 목록 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @DeleteMapping("/reports/{reportId}")
    public ResponseEntity<?> deleteReport(@PathVariable Integer reportId, HttpServletRequest request) {
        try {
            reportService.deleteReport(reportId, CurrentUser.of(request));
            return new ResponseEntity<>(HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("Report 삭제 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}
