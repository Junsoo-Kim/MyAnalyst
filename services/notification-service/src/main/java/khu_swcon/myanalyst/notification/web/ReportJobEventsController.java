package khu_swcon.myanalyst.notification.web;

import jakarta.servlet.http.HttpServletRequest;
import khu_swcon.myanalyst.notification.internal.ReportJobEventStream;
import khu_swcon.myanalyst.shared.web.CurrentUser;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.UUID;

@RestController
public class ReportJobEventsController {
    private final ReportJobEventStream eventStream;

    public ReportJobEventsController(ReportJobEventStream eventStream) {
        this.eventStream = eventStream;
    }

    @GetMapping(value = "/report-jobs/{jobId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable UUID jobId, HttpServletRequest request) {
        // 소유권은 이벤트에 실린 userId로 전송 시점에 확인한다(ReportJobEventStream).
        return eventStream.subscribe(jobId.toString(), CurrentUser.of(request));
    }
}
