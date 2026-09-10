package khu_swcon.myanalyst.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ReportDto {
    private String userid;
    private String title;
    private String chapter;
    private String content;
    private String indicator;
    
    private String evaluations;
    
    private String company;
    private String date;
}
