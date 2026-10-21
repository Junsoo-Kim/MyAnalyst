package khu_swcon.myanalyst.dictionary.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

/** 이 서비스가 쓰는 필드만 읽는다(content 등은 무시). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ReportCreated(Integer reportId, String userId, List<ReportTerm> terms) {
}
