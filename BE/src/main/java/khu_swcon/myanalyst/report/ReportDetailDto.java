package khu_swcon.myanalyst.report;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ReportDetailDto {
    private String title;
    private String chapter;
    private String content;
    private String company;
    private String date;
    private String indicator;
}
