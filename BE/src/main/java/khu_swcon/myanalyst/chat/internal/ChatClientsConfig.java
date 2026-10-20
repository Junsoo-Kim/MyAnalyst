package khu_swcon.myanalyst.chat.internal;

import khu_swcon.myanalyst.shared.web.ServiceClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.Duration;

/**
 * 채팅 모듈이 부르는 두 서비스: 보고서 질의응답(qa-service)과 음성 → 텍스트 변환(stt-service).
 */
@Configuration
public class ChatClientsConfig {

    @Bean
    public WebClient qaWebClient(
            @Value("${app.services.qa.base-url}") String baseUrl,
            @Value("${app.services.connect-timeout}") Duration connectTimeout,
            @Value("${app.services.response-timeout}") Duration responseTimeout) {
        return ServiceClients.create(baseUrl, connectTimeout, responseTimeout);
    }

    @Bean
    public WebClient sttWebClient(
            @Value("${app.services.stt.base-url}") String baseUrl,
            @Value("${app.services.connect-timeout}") Duration connectTimeout,
            @Value("${app.services.response-timeout}") Duration responseTimeout) {
        return ServiceClients.create(baseUrl, connectTimeout, responseTimeout);
    }
}
