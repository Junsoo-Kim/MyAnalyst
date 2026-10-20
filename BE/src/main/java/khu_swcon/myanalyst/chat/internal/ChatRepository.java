package khu_swcon.myanalyst.chat.internal;

import khu_swcon.myanalyst.chat.internal.Chat;
import khu_swcon.myanalyst.report.internal.Report;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ChatRepository extends JpaRepository<Chat, Integer> {
    List<Chat> findByReport(Report report);
}
