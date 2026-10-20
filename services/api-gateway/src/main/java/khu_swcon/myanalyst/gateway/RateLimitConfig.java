package khu_swcon.myanalyst.gateway;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Mono;

import java.net.InetSocketAddress;

@Configuration
public class RateLimitConfig {

    /**
     * 로그인 시도는 클라이언트 IP별로 제한한다(무차별 대입 방지). 로드밸런서 뒤에서는 X-Forwarded-For의 첫 값이
     * 실제 클라이언트다.
     */
    @Bean
    public KeyResolver clientIpKeyResolver() {
        return exchange -> {
            String forwarded = exchange.getRequest().getHeaders().getFirst("X-Forwarded-For");
            if (forwarded != null && !forwarded.isBlank()) {
                return Mono.just(forwarded.split(",")[0].trim());
            }
            InetSocketAddress remote = exchange.getRequest().getRemoteAddress();
            return Mono.just(remote == null ? "unknown" : remote.getAddress().getHostAddress());
        };
    }
}
