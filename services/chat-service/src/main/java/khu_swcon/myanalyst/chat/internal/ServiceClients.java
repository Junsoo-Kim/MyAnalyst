package khu_swcon.myanalyst.chat.internal;

import io.netty.channel.ChannelOption;
import org.slf4j.MDC;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

/**
 * qa/stt를 부르는 WebClient: 연결·응답 타임아웃, 받은 요청의 X-Trace-Id 전파({@link TraceIdFilter}).
 */
final class ServiceClients {

    private ServiceClients() {
    }

    static WebClient create(String baseUrl, Duration connectTimeout, Duration responseTimeout) {
        HttpClient client = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, Math.toIntExact(connectTimeout.toMillis()))
                .responseTimeout(responseTimeout);

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(client))
                .filter(ExchangeFilterFunction.ofRequestProcessor(request -> {
                    String traceId = MDC.get(TraceIdFilter.TRACE_ID);
                    return Mono.just(traceId == null ? request
                            : ClientRequest.from(request).header(TraceIdFilter.HEADER, traceId).build());
                }))
                .build();
    }
}
