package khu_swcon.myanalyst.repository;

import khu_swcon.myanalyst.entity.ReportJobAttempt;
import khu_swcon.myanalyst.entity.ReportJob;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ReportJobAttemptRepository extends JpaRepository<ReportJobAttempt, Long> {
    Optional<ReportJobAttempt> findTopByJobOrderByAttemptNumberDesc(ReportJob job);
}
