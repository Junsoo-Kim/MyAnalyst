package khu_swcon.myanalyst.chat.web;

import khu_swcon.myanalyst.auth.CurrentUser;
import khu_swcon.myanalyst.chat.ChatHistoryDto;
import khu_swcon.myanalyst.chat.ChatRequestDto;
import khu_swcon.myanalyst.chat.ChatResponseDto;
import khu_swcon.myanalyst.chat.ChatService;
import khu_swcon.myanalyst.chat.ChatSttRequestDto;
import khu_swcon.myanalyst.chat.ChatSttResponseDto;
import khu_swcon.myanalyst.shared.ApiException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    /**
     * 사용자 질문에 대한 답변을 생성
     *
     * @param chatRequestDto 채팅 요청 정보 (reportid, question)
     * @return 생성된 답변
     */
    @PostMapping("/chat")
    public ResponseEntity<?> processChat(@RequestBody ChatRequestDto chatRequestDto, HttpServletRequest request) {
        try {
            ChatResponseDto response = chatService.processChat(chatRequestDto, CurrentUser.of(request));
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("답변 생성 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 음성 파일에서 추출한 질문에 대한 답변을 생성
     *
     * @param chatSttRequestDto 음성 채팅 요청 정보 (reportid, audio_file)
     * @return 생성된 질문과 답변
     */
    @PostMapping(value = "/chat/stt", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> processSttChat(@ModelAttribute ChatSttRequestDto chatSttRequestDto, HttpServletRequest request) {
        try {
            ChatSttResponseDto response = chatService.processSttChat(chatSttRequestDto, CurrentUser.of(request));
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("음성 답변 생성 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 리포트 ID로 채팅 기록 조회
     *
     * @param reportId 리포트 ID
     * @return 채팅 기록 목록
     */
    @GetMapping("/reports/{reportId}/chat")
    public ResponseEntity<?> getChatHistoryByReportId(@PathVariable Integer reportId, HttpServletRequest request) {
        try {
            List<ChatHistoryDto> chats = chatService.getChatHistoryByReportId(reportId, CurrentUser.of(request));
            return new ResponseEntity<>(chats, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("채팅 기록 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}
