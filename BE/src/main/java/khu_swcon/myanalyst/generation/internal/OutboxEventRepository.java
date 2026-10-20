package khu_swcon.myanalyst.generation.internal;

import jakarta.persistence.LockModeType;
import khu_swcon.myanalyst.generation.internal.OutboxEvent;
import khu_swcon.myanalyst.generation.internal.OutboxEventStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface OutboxEventRepository extends JpaRepository<OutboxEvent, UUID> {
    List<OutboxEvent> findTop10ByStatusAndAvailableAtLessThanEqualOrderByCreatedAtAsc(
            OutboxEventStatus status, Instant now);

    List<OutboxEvent> findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(
            OutboxEventStatus status, Instant now);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<OutboxEvent> findWithLockByEventId(UUID eventId);
}
