package khu_swcon.myanalyst.controller;

import jakarta.validation.Valid;
import jakarta.servlet.http.HttpSession;
import khu_swcon.myanalyst.dto.ReportJobRequestDto;
import khu_swcon.myanalyst.dto.ReportJobResponseDto;
import khu_swcon.myanalyst.service.ReportJobService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

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
        ReportJobResponseDto response = reportJobService.enqueue(request, currentUser(session), idempotencyKey);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .header(HttpHeaders.LOCATION, "/report-jobs/" + response.getJobId())
                .body(response);
    }

    @GetMapping("/{jobId}")
    public ReportJobResponseDto get(@PathVariable UUID jobId, HttpSession session) {
        return reportJobService.getJob(jobId, currentUser(session));
    }

    @PostMapping("/{jobId}/cancel")
    public ReportJobResponseDto cancel(@PathVariable UUID jobId, HttpSession session) {
        return reportJobService.cancel(jobId, currentUser(session));
    }

    @GetMapping(value = "/{jobId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable UUID jobId, HttpSession session) {
        return reportJobService.subscribe(jobId, currentUser(session));
    }

    private String currentUser(HttpSession session) {
        return (String) session.getAttribute("userId");
    }
}
