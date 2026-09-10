package khu_swcon.myanalyst.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ReportJobRequestDto {
    @NotBlank @Size(max = 500)
    private String title;
    @NotBlank
    private String chapter;
    @Size(max = 500)
    private String indicator;
    private String evaluations;
    @NotBlank @Size(max = 200)
    private String company;
    @NotBlank @Size(max = 100)
    private String date;
}
