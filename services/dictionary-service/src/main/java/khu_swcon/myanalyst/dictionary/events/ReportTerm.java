package khu_swcon.myanalyst.dictionary.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ReportTerm(String term, String explanation) {
}
