package khu_swcon.myanalyst.generation.internal;

import khu_swcon.myanalyst.generation.internal.ReportJobAttempt;
import khu_swcon.myanalyst.generation.internal.ReportJob;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ReportJobAttemptRepository extends JpaRepository<ReportJobAttempt, Long> {
    Optional<ReportJobAttempt> findTopByJobOrderByAttemptNumberDesc(ReportJob job);
}
