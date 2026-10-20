package khu_swcon.myanalyst.chat.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * {@code report.created}로 받은 보고서 사본: 권한 확인용 소유자와 질의응답에 넘길 본문.
 * 질문마다 보고서 서비스를 부르지 않으므로 보고서 서비스가 내려가 있어도 채팅은 동작한다.
 */
@Entity
@Table(name = "chat_reports")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class ChatReport {

    @Id
    @Column(name = "report_id")
    private Integer reportId;

    @Column(name = "user_id", nullable = false)
    private String userId;

    @Column(name = "content", columnDefinition = "TEXT")
    private String content;
}
