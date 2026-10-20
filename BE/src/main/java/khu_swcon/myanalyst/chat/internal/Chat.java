package khu_swcon.myanalyst.chat.internal;

import khu_swcon.myanalyst.report.internal.Report;
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

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reportid") // DB에서 ON DELETE CASCADE 설정됨
    private Report report;

    @Column(name = "question", columnDefinition = "TEXT")
    private String question;

    @Column(name = "answer", columnDefinition = "TEXT")
    private String answer;
}