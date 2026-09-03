package khu_swcon.myanalyst.service;

import khu_swcon.myanalyst.dto.ChatRequestDto;
import khu_swcon.myanalyst.dto.ChatResponseDto;
import khu_swcon.myanalyst.dto.ChatHistoryDto;
import khu_swcon.myanalyst.dto.ChatSttRequestDto;
import khu_swcon.myanalyst.dto.ChatSttResponseDto;
import khu_swcon.myanalyst.entity.Chat;
import khu_swcon.myanalyst.entity.Report;
import khu_swcon.myanalyst.exception.ApiException;
import khu_swcon.myanalyst.repository.ChatRepository;
import khu_swcon.myanalyst.repository.ReportRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class ChatService {
    
    private final ChatRepository chatRepository;
    private final ReportRepository reportRepository;
    private final WebClient webClient;

    @Value("${rag.server.base-url}")
    private String ragServerBaseUrl;

    @Autowired
    public ChatService(ChatRepository chatRepository, ReportRepository reportRepository) {
        this.chatRepository = chatRepository;
        this.reportRepository = reportRepository;
        this.webClient = WebClient.create();
    }
    
    /**
     * 사용자 질문에 대한 답변을 생성하고 저장
     * 
     * @param chatRequestDto 채팅 요청 정보
     * @return 생성된 답변
     */
    @Transactional
    public ChatResponseDto processChat(ChatRequestDto chatRequestDto) {
        // 1. 리포트 존재 여부 확인
        Report report = reportRepository.findById(chatRequestDto.getReportid())
                .orElseThrow(() -> new ApiException("Report not found with ID: " + chatRequestDto.getReportid(), HttpStatus.NOT_FOUND));
        
        // 2. 외부 API 호출하여 답변 생성
        Map<String, String> requestBody = new HashMap<>();
        requestBody.put("report", report.getContent());
        requestBody.put("question", chatRequestDto.getQuestion());
        
        try {
            Map<String, Object> response = webClient.post()
                    .uri(ragServerBaseUrl + "/questions")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(Map.class)
                    .block(); // 동기적으로 응답 대기
            
            if (response == null || !response.containsKey("answer")) {
                throw new ApiException("답변 생성 API 호출 결과가 유효하지 않습니다.", HttpStatus.INTERNAL_SERVER_ERROR);
            }
            
            String answer = (String) response.get("answer");
            
            // 3. Chat 엔티티 생성 및 저장
            Chat chat = Chat.builder()
                    .report(report)
                    .question(chatRequestDto.getQuestion())
                    .answer(answer)
                    .build();
            
            chatRepository.save(chat);
            
            // 4. 응답 생성
            return ChatResponseDto.builder()
                    .answer(answer)
                    .build();
            
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException("답변 생성 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    
    /**
     * 리포트 ID로 채팅 기록을 조회
     * 
     * @param reportId 리포트 ID
     * @return 채팅 기록 목록
     */
    @Transactional(readOnly = true)
    public List<ChatHistoryDto> getChatHistoryByReportId(Integer reportId) {
        // 1. 리포트 존재 여부 확인
        Report report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException("Report not found with ID: " + reportId, HttpStatus.NOT_FOUND));
        
        // 2. 채팅 기록 조회
        List<Chat> chats = chatRepository.findByReport(report);
        
        // 3. 응답 생성
        return chats.stream()
                .map(chat -> ChatHistoryDto.builder()
                        .chatid(chat.getChatid())
                        .question(chat.getQuestion())
                        .answer(chat.getAnswer())
                        .build())
                .collect(Collectors.toList());
    }
    
    /**
     * 음성 파일에서 추출한 질문에 대한 답변을 생성하고 저장
     * 
     * @param chatSttRequestDto 음성 채팅 요청 정보
     * @return 생성된 질문과 답변
     */
    @Transactional
    public ChatSttResponseDto processSttChat(ChatSttRequestDto chatSttRequestDto) {
        // 1. 리포트 존재 여부 확인
        Report report = reportRepository.findById(chatSttRequestDto.getReportid())
                .orElseThrow(() -> new ApiException("Report not found with ID: " + chatSttRequestDto.getReportid(), HttpStatus.NOT_FOUND));
        
        try {
            // 2. 외부 API 호출을 위한 멀티파트 요청 구성
            MultipartBodyBuilder builder = new MultipartBodyBuilder();
            builder.part("report", report.getContent());
            
            // 음성 파일 처리 - 디버그 로그 추가
            if (chatSttRequestDto.getAudio_file() != null) {
                System.out.println("Audio file name: " + chatSttRequestDto.getAudio_file().getOriginalFilename());
                System.out.println("Audio file size: " + chatSttRequestDto.getAudio_file().getSize());
                System.out.println("Audio file content type: " + chatSttRequestDto.getAudio_file().getContentType());
                
                try {
                    byte[] audioFileBytes = chatSttRequestDto.getAudio_file().getBytes();
                    // 파일 확장자 확인
                    String originalFilename = chatSttRequestDto.getAudio_file().getOriginalFilename();
                    String filename = originalFilename != null ? originalFilename : "audio.m4a";
                    
                    // 모든 오디오 파일 타입을 허용
                    builder.part("audio_file", new ByteArrayResource(audioFileBytes))
                           .filename(filename)
                           .contentType(MediaType.parseMediaType(chatSttRequestDto.getAudio_file().getContentType() != null 
                                                                ? chatSttRequestDto.getAudio_file().getContentType() 
                                                                : "audio/mp4"));
                } catch (IOException e) {
                    throw new ApiException("Failed to process audio file: " + e.getMessage(), HttpStatus.BAD_REQUEST);
                }
            } else {
                throw new ApiException("Audio file is required", HttpStatus.BAD_REQUEST);
            }
            
            // 3. 외부 API 호출
            Map<String, Object> response = webClient.post()
                    .uri(ragServerBaseUrl + "/questions/stt")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(BodyInserters.fromMultipartData(builder.build()))
                    .retrieve()
                    .bodyToMono(Map.class)
                    .block();
            
            if (response == null || !response.containsKey("answer") || !response.containsKey("question")) {
                throw new ApiException("STT 답변 생성 API 호출 결과가 유효하지 않습니다.", HttpStatus.INTERNAL_SERVER_ERROR);
            }
            
            String question = (String) response.get("question");
            String answer = (String) response.get("answer");
            
            // 4. Chat 엔티티 생성 및 저장
            Chat chat = Chat.builder()
                    .report(report)
                    .question(question)
                    .answer(answer)
                    .build();
            
            chatRepository.save(chat);
            
            // 5. 응답 생성
            return ChatSttResponseDto.builder()
                    .question(question)
                    .answer(answer)
                    .build();
            
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            e.printStackTrace(); // 스택 트레이스 출력
            throw new ApiException("STT 답변 생성 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}
