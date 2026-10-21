package khu_swcon.myanalyst.chat;

import com.fasterxml.jackson.databind.ObjectMapper;
import khu_swcon.myanalyst.chat.events.ReportCreated;
import khu_swcon.myanalyst.chat.events.ReportDeleted;
import khu_swcon.myanalyst.chat.events.ReportEvents;
import khu_swcon.myanalyst.chat.internal.Chat;
import khu_swcon.myanalyst.chat.internal.ChatReport;
import khu_swcon.myanalyst.chat.internal.ChatReportRepository;
import khu_swcon.myanalyst.chat.internal.ChatRepository;
import khu_swcon.myanalyst.shared.ApiException;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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
    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    private final ChatRepository chatRepository;
    private final ChatReportRepository reportRepository;
    private final ObjectMapper objectMapper;
    private final WebClient qaWebClient;
    private final WebClient sttWebClient;

    public ChatService(ChatRepository chatRepository, ChatReportRepository reportRepository, ObjectMapper objectMapper,
                       @Qualifier("qaWebClient") WebClient qaWebClient,
                       @Qualifier("sttWebClient") WebClient sttWebClient) {
        this.chatRepository = chatRepository;
        this.reportRepository = reportRepository;
        this.objectMapper = objectMapper;
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
        // 1. 리포트 소유권 확인 및 본문 조회 (report.created로 받아 둔 사본)
        String reportContent = findOwnedReport(chatRequestDto.getReportid(), userId).getContent();

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
        findOwnedReport(reportId, userId);

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
        String reportContent = findOwnedReport(chatSttRequestDto.getReportid(), userId).getContent();
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

    /**
     * 사본이 없으면(이벤트 도착 전이거나 삭제된 보고서) 404. 보고서가 막 만들어진 직후에는 사본이 수십~수백 ms 늦게
     * 생길 수 있다(최종 일관성).
     */
    private ChatReport findOwnedReport(Integer reportId, String userId) {
        ChatReport report = reportRepository.findById(reportId)
                .orElseThrow(() -> new ApiException("Report not found with ID: " + reportId, HttpStatus.NOT_FOUND));
        if (!report.getUserId().equals(userId)) {
            throw new ApiException("You do not have access to this report", HttpStatus.FORBIDDEN);
        }
        return report;
    }

    /**
     * Kafka {@code report.created}(compacted)를 소비해 보고서 사본을 만들고, 같은 토픽·같은 key로 오는
     * ReportDeleted로 사본과 채팅 기록을 지운다. 둘 다 멱등이라 offset을 처음으로 되돌려 다시 읽어도(재생) 결과가 같다.
     */
    @KafkaListener(topics = ReportEvents.TOPIC, groupId = "chat")
    @Transactional
    public void on(ConsumerRecord<String, byte[]> record) throws IOException {
        String eventType = ReportEvents.eventType(record);
        switch (eventType) {
            case ReportEvents.CREATED -> {
                ReportCreated event = objectMapper.readValue(record.value(), ReportCreated.class);
                reportRepository.save(new ChatReport(event.reportId(), event.userId(), event.content()));
            }
            case ReportEvents.DELETED -> {
                ReportDeleted event = objectMapper.readValue(record.value(), ReportDeleted.class);
                chatRepository.deleteByReportId(event.reportId());
                reportRepository.deleteById(event.reportId());
            }
            default -> log.warn("알 수 없는 이벤트 타입 무시: {} (offset={})", eventType, record.offset());
        }
    }
}
