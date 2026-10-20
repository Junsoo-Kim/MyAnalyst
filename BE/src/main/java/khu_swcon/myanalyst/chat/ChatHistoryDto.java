package khu_swcon.myanalyst.chat;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ChatHistoryDto {
    private Integer chatid;
    private String question;
    private String answer;
}
