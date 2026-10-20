package khu_swcon.myanalyst.shared.events;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.modulith.events.IncompleteEventPublications;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 리스너가 실패해 완료되지 못한 이벤트 발행을 주기적으로 다시 전달한다.
 * 재기동 시 재전달(republish-outstanding-events-on-restart)과 함께, 자체 Outbox relay가 하던 재시도를 대신한다.
 */
@Component
public class IncompleteEventResubmitter {
    private final IncompleteEventPublications incompleteEvents;
    private final Duration resubmitAfter;

    public IncompleteEventResubmitter(
            IncompleteEventPublications incompleteEvents,
            @Value("${app.events.resubmit-after:30s}") Duration resubmitAfter) {
        this.incompleteEvents = incompleteEvents;
        this.resubmitAfter = resubmitAfter;
    }

    @Scheduled(fixedDelayString = "${app.events.resubmit-interval-ms:30000}")
    public void resubmit() {
        incompleteEvents.resubmitIncompletePublicationsOlderThan(resubmitAfter);
    }
}
