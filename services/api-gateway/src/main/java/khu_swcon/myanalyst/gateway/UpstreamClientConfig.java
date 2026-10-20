package khu_swcon.myanalyst.gateway;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.config.HttpClientCustomizer;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.UnknownHostException;
import java.time.Duration;

@Configuration
public class UpstreamClientConfig {

    /**
     * 뒤쪽 서비스 주소의 DNS 캐시를 짧게 둔다.
     *
     * <p>4단계 검증 중 발견: auth-service와 user-service를 재시작하자 두 컨테이너의 IP가 서로 바뀌었는데, Gateway는
     * 재시작 전 IP를 계속 써서 로그인 요청(POST /sessions)이 user-service로 가 404가 났다. reactor-netty 리졸버가
     * DNS 응답의 TTL(Docker 내장 DNS는 600초)만큼 캐시했기 때문이다. 실패보다 위험한 "다른 서비스로 잘못 감"이라
     * 캐시 상한을 몇 초로 줄인다. ECS Service Connect·Cloud Map 같은 환경에서도 같은 문제가 생길 수 있다.
     */
    @Bean
    public HttpClientCustomizer shortDnsCache(@Value("${app.upstream.dns-cache-max-ttl:5s}") Duration maxTtl) {
        return httpClient -> httpClient.resolver(spec -> spec
                .cacheMaxTimeToLive(maxTtl)
                .cacheNegativeTimeToLive(Duration.ZERO));
    }

    /**
     * 뒤쪽 서비스에 연결하지 못하면 500 대신 503을 돌려준다. 클라이언트가 "잠시 후 재시도"로 해석할 수 있게 한다.
     */
    @Bean
    public GlobalFilter upstreamUnavailableFilter() {
        return new GlobalFilter() {
            @Override
            public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
                return chain.filter(exchange).onErrorResume(UpstreamClientConfig::isConnectFailure, error -> {
                    exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
                    return exchange.getResponse().setComplete();
                });
            }
        };
    }

    private static boolean isConnectFailure(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof ConnectException || t instanceof NoRouteToHostException
                    || t instanceof UnknownHostException
                    || t.getClass().getName().equals("io.netty.channel.ConnectTimeoutException")) {
                return true;
            }
        }
        return false;
    }
}
