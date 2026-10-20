package khu_swcon.myanalyst.dictionary.internal;

import khu_swcon.myanalyst.dictionary.internal.Dictionary;
import khu_swcon.myanalyst.report.internal.Report;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DictionaryRepository extends JpaRepository<Dictionary, Integer> {
    List<Dictionary> findByReport(Report report);
    void deleteByReport(Report report);
}
