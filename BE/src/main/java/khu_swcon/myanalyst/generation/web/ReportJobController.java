package khu_swcon.myanalyst.generation.web;

import jakarta.validation.Valid;
import jakarta.servlet.http.HttpSession;
import khu_swcon.myanalyst.auth.CurrentUser;
import khu_swcon.myanalyst.generation.ReportJobRequestDto;
import khu_swcon.myanalyst.generation.ReportJobResponseDto;
import khu_swcon.myanalyst.generation.ReportJobService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/report-jobs")
public class ReportJobController {
    private final ReportJobService reportJobService;

    public ReportJobController(ReportJobService reportJobService) {
        this.reportJobService = reportJobService;
    }

    @PostMapping
    public ResponseEntity<ReportJobResponseDto> create(
            @Valid @RequestBody ReportJobRequestDto request,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            HttpSession session) {
        ReportJobResponseDto response = reportJobService.enqueue(request, CurrentUser.of(session), idempotencyKey);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .header(HttpHeaders.LOCATION, "/report-jobs/" + response.getJobId())
                .body(response);
    }

    @GetMapping("/{jobId}")
    public ReportJobResponseDto get(@PathVariable UUID jobId, HttpSession session) {
        return reportJobService.getJob(jobId, CurrentUser.of(session));
    }

    @PostMapping("/{jobId}/cancel")
    public ReportJobResponseDto cancel(@PathVariable UUID jobId, HttpSession session) {
        return reportJobService.cancel(jobId, CurrentUser.of(session));
    }
}
