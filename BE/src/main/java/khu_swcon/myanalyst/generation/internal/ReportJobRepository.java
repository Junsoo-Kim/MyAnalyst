package khu_swcon.myanalyst.generation.internal;

import khu_swcon.myanalyst.generation.internal.ReportJob;
import khu_swcon.myanalyst.generation.ReportJobStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ReportJobRepository extends JpaRepository<ReportJob, UUID> {
    Optional<ReportJob> findByUser_UseridAndIdempotencyKey(String userId, String idempotencyKey);
    Optional<ReportJob> findByJobIdAndUser_Userid(UUID jobId, String userId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<ReportJob> findWithLockByJobId(UUID jobId);

    List<ReportJob> findTop10ByStatusInAndNextAttemptAtLessThanEqualOrderByCreatedAtAsc(
            List<ReportJobStatus> statuses, Instant now);

    List<ReportJob> findTop10ByStatusAndLeaseExpiresAtLessThanOrderByCreatedAtAsc(
            ReportJobStatus status, Instant leaseExpiresAt);
}
