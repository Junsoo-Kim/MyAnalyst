package khu_swcon.myanalyst.dictionary.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DictionaryRepository extends JpaRepository<Dictionary, Integer> {
    List<Dictionary> findByReportId(Integer reportId);
    boolean existsByReportId(Integer reportId);
    void deleteByReportId(Integer reportId);
}
