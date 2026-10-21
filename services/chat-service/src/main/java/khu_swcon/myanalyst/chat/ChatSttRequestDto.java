package khu_swcon.myanalyst.chat;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.web.multipart.MultipartFile;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ChatSttRequestDto {
    private Integer reportid;
    private MultipartFile audio_file;
}
