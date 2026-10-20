package khu_swcon.myanalyst.chat;

import khu_swcon.myanalyst.chat.internal.Chat;
import khu_swcon.myanalyst.chat.internal.ChatRepository;
import khu_swcon.myanalyst.report.ReportDeleted;
import khu_swcon.myanalyst.report.ReportService;
import khu_swcon.myanalyst.shared.ApiException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.kafka.annotation.KafkaListener;
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
    private final ReportService reportService;
    private final WebClient qaWebClient;
    private final WebClient sttWebClient;

    public ChatService(ChatRepository chatRepository, ReportService reportService,
                       @Qualifier("qaWebClient") WebClient qaWebClient,
                       @Qualifier("sttWebClient") WebClient sttWebClient) {
        this.chatRepository = chatRepository;
        this.reportService = reportService;
        this.qaWebClient = qaWebClient;
        this.sttWebClient = sttWebClient;
    }

    /**
     * 사용자 질문에 대한 답변을 생성하고 저장
     *
     * @param chatRequestDto 채팅 요청 정보
     * @return 생성된 답변
     */
    @Transactional
    public ChatResponseDto processChat(ChatRequestDto chatRequestDto, String userId) {
        // 1. 리포트 소유권 확인 및 본문 조회
        String reportContent = reportService.getOwnedReportContent(chatRequestDto.getReportid(), userId);

        try {
            // 2. qa-service로 답변 생성
            String answer = askQuestion(reportContent, chatRequestDto.getQuestion());

            // 3. Chat 엔티티 생성 및 저장
            chatRepository.save(Chat.builder()
                    .reportId(chatRequestDto.getReportid())
                    .question(chatRequestDto.getQuestion())
                    .answer(answer)
                    .build());

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
    public List<ChatHistoryDto> getChatHistoryByReportId(Integer reportId, String userId) {
        // 1. 리포트 소유권 확인
        reportService.assertOwnedBy(reportId, userId);

        // 2. 채팅 기록 조회 및 응답 생성
        return chatRepository.findByReportId(reportId).stream()
                .map(chat -> ChatHistoryDto.builder()
                        .chatid(chat.getChatid())
                        .question(chat.getQuestion())
                        .answer(chat.getAnswer())
                        .build())
                .collect(Collectors.toList());
    }

    /**
     * 음성 파일에서 추출한 질문에 대한 답변을 생성하고 저장.
     * stt-service가 음성을 텍스트로 바꾸고, 그 텍스트를 일반 질문과 같은 qa-service 경로로 보낸다.
     *
     * @param chatSttRequestDto 음성 채팅 요청 정보
     * @return 생성된 질문과 답변
     */
    @Transactional
    public ChatSttResponseDto processSttChat(ChatSttRequestDto chatSttRequestDto, String userId) {
        // 1. 리포트 소유권 확인 및 본문 조회
        String reportContent = reportService.getOwnedReportContent(chatSttRequestDto.getReportid(), userId);
        if (chatSttRequestDto.getAudio_file() == null) {
            throw new ApiException("Audio file is required", HttpStatus.BAD_REQUEST);
        }

        try {
            // 2. 음성 → 텍스트 (stt-service)
            String question = transcribe(chatSttRequestDto);

            // 3. 질문 답변 (qa-service)
            String answer = askQuestion(reportContent, question);

            // 4. Chat 엔티티 생성 및 저장
            chatRepository.save(Chat.builder()
                    .reportId(chatSttRequestDto.getReportid())
                    .question(question)
                    .answer(answer)
                    .build());

            // 5. 응답 생성
            return ChatSttResponseDto.builder()
                    .question(question)
                    .answer(answer)
                    .build();

        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException("STT 답변 생성 중 오류 발생: " + e.getMessage(), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    private String askQuestion(String reportContent, String question) {
        Map<String, String> requestBody = new HashMap<>();
        requestBody.put("report", reportContent);
        requestBody.put("question", question);

        Map<String, Object> response = qaWebClient.post()
                .uri("/questions")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(Map.class)
                .block(); // 동기적으로 응답 대기

        if (response == null || !response.containsKey("answer")) {
            throw new ApiException("답변 생성 API 호출 결과가 유효하지 않습니다.", HttpStatus.INTERNAL_SERVER_ERROR);
        }
        return (String) response.get("answer");
    }

    private String transcribe(ChatSttRequestDto chatSttRequestDto) {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        try {
            byte[] audioFileBytes = chatSttRequestDto.getAudio_file().getBytes();
            String originalFilename = chatSttRequestDto.getAudio_file().getOriginalFilename();
            String filename = originalFilename != null ? originalFilename : "audio.m4a";
            String contentType = chatSttRequestDto.getAudio_file().getContentType();

            // 모든 오디오 파일 타입을 허용 (형식 검증은 stt-service가 한다)
            builder.part("audio_file", new ByteArrayResource(audioFileBytes))
                   .filename(filename)
                   .contentType(MediaType.parseMediaType(contentType != null ? contentType : "audio/mp4"));
        } catch (IOException e) {
            throw new ApiException("Failed to process audio file: " + e.getMessage(), HttpStatus.BAD_REQUEST);
        }

        Map<String, Object> response = sttWebClient.post()
                .uri("/transcriptions")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(builder.build()))
                .retrieve()
                .bodyToMono(Map.class)
                .block();

        if (response == null || !response.containsKey("text")) {
            throw new ApiException("STT API 호출 결과가 유효하지 않습니다.", HttpStatus.INTERNAL_SERVER_ERROR);
        }
        return (String) response.get("text");
    }

    /** Kafka {@code report.deleted}를 소비해 그 보고서의 채팅 기록을 지운다. 다시 와도 결과가 같다(멱등). */
    @KafkaListener(topics = ReportDeleted.TOPIC, groupId = "chat")
    @Transactional
    public void on(ReportDeleted event) {
        chatRepository.deleteByReportId(event.reportId());
    }
}
