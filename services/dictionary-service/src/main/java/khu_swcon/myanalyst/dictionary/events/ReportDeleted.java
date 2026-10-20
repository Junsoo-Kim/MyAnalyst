package khu_swcon.myanalyst.dictionary.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ReportDeleted(Integer reportId) {
}
