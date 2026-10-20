package khu_swcon.myanalyst.report;

/**
 * 보고서가 삭제됐다는 도메인 이벤트. DB cascade 대신 이 이벤트로 채팅·용어 데이터를 정리한다.
 */
public record ReportDeleted(Integer reportId) {
}
