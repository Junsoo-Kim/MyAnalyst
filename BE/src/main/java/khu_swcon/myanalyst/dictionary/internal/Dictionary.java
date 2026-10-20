package khu_swcon.myanalyst.dictionary.internal;

import khu_swcon.myanalyst.report.internal.Report;
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

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "dictid")
    private Integer dictid;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reportid") // DB에서 ON DELETE SET NULL로 설정되어 있으므로, nullable = true (기본값)
    private Report report;

    @Column(name = "word", nullable = false, length = 20)
    private String word;

    @Column(name = "detail", columnDefinition = "TEXT")
    private String detail;
}