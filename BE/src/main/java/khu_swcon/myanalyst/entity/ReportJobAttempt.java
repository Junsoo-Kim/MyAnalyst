package khu_swcon.myanalyst.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

@Entity
@Table(name = "report_job_attempt")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ReportJobAttempt {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "job_id", nullable = false)
    private ReportJob job;

    @Column(nullable = false)
    private int attemptNumber;

    @Column(nullable = false)
    private Instant startedAt;

    private Instant finishedAt;

    @Column(columnDefinition = "TEXT")
    private String error;
}
