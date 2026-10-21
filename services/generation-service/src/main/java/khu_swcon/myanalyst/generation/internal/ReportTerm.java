package khu_swcon.myanalyst.generation.internal;

/**
 * RAG가 보고서에서 뽑아낸 도메인 용어. 워커의 완료 이벤트로 받아 저장 명령에 그대로 넘긴다.
 */
public record ReportTerm(String term, String explanation) {
}
