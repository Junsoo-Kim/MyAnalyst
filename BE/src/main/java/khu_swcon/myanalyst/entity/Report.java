package khu_swcon.myanalyst.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.ArrayList;
import java.util.List;
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

    @ManyToOne(fetch = FetchType.LAZY) // 지연 로딩이 성능에 유리할 수 있음
    @JoinColumn(name = "userid", nullable = false)
    private User user;

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

    @OneToMany(mappedBy = "report")
    private List<Dictionary> dictionaryEntries = new ArrayList<>();

    @OneToMany(mappedBy = "report", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<Chat> chats = new ArrayList<>();
}
