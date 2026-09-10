package khu_swcon.myanalyst.config;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import khu_swcon.myanalyst.observability.TraceContext;

import java.time.Duration;

@Configuration
public class RagClientConfig {

    @Bean
    public WebClient ragWebClient(
            @Value("${app.rag.base-url}") String baseUrl,
            @Value("${app.rag.connect-timeout}") Duration connectTimeout,
            @Value("${app.rag.response-timeout}") Duration responseTimeout) {
        HttpClient client = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, Math.toIntExact(connectTimeout.toMillis()))
                .responseTimeout(responseTimeout);

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(client))
                .filter(ExchangeFilterFunction.ofRequestProcessor(request ->
                        reactor.core.publisher.Mono.just(ClientRequest.from(request)
                                .header("X-Trace-Id", TraceContext.currentTraceId())
                                .build())))
                .build();
    }
}
