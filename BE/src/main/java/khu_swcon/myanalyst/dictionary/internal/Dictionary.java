package khu_swcon.myanalyst.dictionary.internal;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

@Entity
@Table(name = "Dictionary") // 실제 테이블명 Dictionary에 매핑
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Dictionary {

    public static final int MAX_WORD_LENGTH = 20;

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "dictid")
    private Integer dictid;

    // 보고서 모듈의 엔티티 대신 ID만 보관한다. 보고서 삭제는 ReportDeleted 이벤트로 정리한다.
    @Column(name = "reportid")
    private Integer reportId;

    @Column(name = "word", nullable = false, length = MAX_WORD_LENGTH)
    private String word;

    @Column(name = "detail", columnDefinition = "TEXT")
    private String detail;
}
