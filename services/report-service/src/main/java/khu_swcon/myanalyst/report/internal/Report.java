package khu_swcon.myanalyst.report.internal;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.UUID;

@Entity
@Table(name = "Reports") // 실제 테이블명 Reports에 매핑
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Report {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY) // PostgreSQL의 SERIAL 타입 매핑
    @Column(name = "reportid")
    private Integer reportid;

    // 사용자 모듈의 엔티티 대신 ID만 보관한다. 모듈(이후 서비스) 사이에는 FK를 두지 않는다.
    @Column(name = "userid", nullable = false, length = 20)
    private String userId;

    @Column(name = "title", nullable = false, columnDefinition = "TEXT")
    private String title;

    @Column(name = "chapter", columnDefinition = "TEXT")
    private String chapter;

    @Column(name = "content", columnDefinition = "TEXT")
    private String content;

    @Column(name = "indicator", columnDefinition = "TEXT")
    private String indicator;

    @Column(name = "company", columnDefinition = "TEXT")
    private String company;

    @Column(name = "date", columnDefinition = "TEXT")
    private String date;

    @Column(name = "generation_job_id", unique = true)
    private UUID generationJobId;
}
