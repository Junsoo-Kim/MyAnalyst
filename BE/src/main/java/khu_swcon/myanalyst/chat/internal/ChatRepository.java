package khu_swcon.myanalyst.chat.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ChatRepository extends JpaRepository<Chat, Integer> {
    List<Chat> findByReportId(Integer reportId);
    void deleteByReportId(Integer reportId);
}
