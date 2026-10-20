package khu_swcon.myanalyst.dictionary.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * {@code report.created}로 받은 보고서 소유자 사본. 조회 요청의 권한 확인에 쓴다(보고서 서비스 동기 호출 없음).
 */
@Entity
@Table(name = "dictionary_reports")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class DictionaryReport {

    @Id
    @Column(name = "report_id")
    private Integer reportId;

    @Column(name = "user_id", nullable = false)
    private String userId;
}
