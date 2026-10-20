package khu_swcon.myanalyst.notification.web;

import jakarta.servlet.http.HttpSession;
import khu_swcon.myanalyst.auth.CurrentUser;
import khu_swcon.myanalyst.generation.ReportJobService;
import khu_swcon.myanalyst.notification.internal.ReportJobEventStream;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.UUID;

@RestController
public class ReportJobEventsController {
    private final ReportJobService reportJobService;
    private final ReportJobEventStream eventStream;

    public ReportJobEventsController(ReportJobService reportJobService, ReportJobEventStream eventStream) {
        this.reportJobService = reportJobService;
        this.eventStream = eventStream;
    }

    @GetMapping(value = "/report-jobs/{jobId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable UUID jobId, HttpSession session) {
        // 소유권 확인과 현재 상태 조회는 생성 모듈의 공개 API로 한다.
        return eventStream.subscribe(reportJobService.getJob(jobId, CurrentUser.of(session)));
    }
}
