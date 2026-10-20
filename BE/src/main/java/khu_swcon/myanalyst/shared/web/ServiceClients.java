package khu_swcon.myanalyst.shared.web;

import io.netty.channel.ChannelOption;
import khu_swcon.myanalyst.shared.observability.TraceContext;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

/**
 * 다른 서비스(market-data, qa, stt)를 부르는 WebClient를 같은 규칙으로 만든다: 연결·응답 타임아웃,
 * 요청마다 X-Trace-Id 전파. 어느 서비스를 부를지는 각 모듈이 자기 설정에서 정한다.
 */
public final class ServiceClients {

    private ServiceClients() {
    }

    public static WebClient create(String baseUrl, Duration connectTimeout, Duration responseTimeout) {
        HttpClient client = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, Math.toIntExact(connectTimeout.toMillis()))
                .responseTimeout(responseTimeout);

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(client))
                .filter(ExchangeFilterFunction.ofRequestProcessor(request ->
                        Mono.just(ClientRequest.from(request)
                                .header("X-Trace-Id", TraceContext.currentTraceId())
                                .build())))
                .build();
    }
}
