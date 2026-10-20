package khu_swcon.myanalyst.chat.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** 이 서비스가 쓰는 필드만 읽는다(terms 등은 무시). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ReportCreated(Integer reportId, String userId, String content) {
}
