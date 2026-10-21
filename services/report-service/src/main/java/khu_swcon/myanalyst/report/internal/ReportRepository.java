package khu_swcon.myanalyst.report.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface ReportRepository extends JpaRepository<Report, Integer> {
    List<Report> findByUserId(String userId);
    Optional<Report> findByGenerationJobId(UUID generationJobId);
}
