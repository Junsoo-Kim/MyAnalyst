package khu_swcon.myanalyst.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserDto {
    @NotBlank
    @Size(max = 20)
    private String userid;
    @NotBlank
    @Size(min = 8, max = 72)
    private String password;
}
