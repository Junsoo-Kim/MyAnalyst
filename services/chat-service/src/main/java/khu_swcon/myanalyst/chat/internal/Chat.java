package khu_swcon.myanalyst.chat.internal;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

@Entity
@Table(name = "Chats") // 실제 테이블명 Chats에 매핑
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Chat {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "chatid")
    private Integer chatid;

    // 보고서 서비스의 ID만 보관한다. 보고서 삭제는 report.created 토픽의 ReportDeleted 이벤트로 정리한다.
    @Column(name = "reportid")
    private Integer reportId;

    @Column(name = "question", columnDefinition = "TEXT")
    private String question;

    @Column(name = "answer", columnDefinition = "TEXT")
    private String answer;
}
