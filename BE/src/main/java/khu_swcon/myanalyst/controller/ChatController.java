package khu_swcon.myanalyst.controller;

import khu_swcon.myanalyst.dto.ChatRequestDto;
import khu_swcon.myanalyst.dto.ChatResponseDto;
import khu_swcon.myanalyst.dto.ChatSttRequestDto;
import khu_swcon.myanalyst.dto.ChatSttResponseDto;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.service.ChatService;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ChatController {
    
    private final ChatService chatService;
    
    @Autowired
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
    public ResponseEntity<?> processChat(@RequestBody ChatRequestDto chatRequestDto, HttpSession session) {
        try {
            ChatResponseDto response = chatService.processChat(chatRequestDto, currentUser(session));
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
    public ResponseEntity<?> processSttChat(@ModelAttribute ChatSttRequestDto chatSttRequestDto, HttpSession session) {
        try {
            ChatSttResponseDto response = chatService.processSttChat(chatSttRequestDto, currentUser(session));
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("음성 답변 생성 중 오류가 발생했습니다: " + e.getMessage(), 
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    private String currentUser(HttpSession session) {
        return (String) session.getAttribute("userId");
    }
}
