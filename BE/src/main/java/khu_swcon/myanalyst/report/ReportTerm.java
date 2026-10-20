package khu_swcon.myanalyst.report;

/**
 * RAG가 보고서에서 뽑아낸 도메인 용어. 보고서와 함께 생성되어 {@link ReportCreated}로 전달된다.
 */
public record ReportTerm(String term, String explanation) {
}
