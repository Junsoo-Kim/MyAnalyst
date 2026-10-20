package khu_swcon.myanalyst.gateway;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * 뒤쪽 서비스로 보내기 전에 신원 헤더를 다시 쓴다.
 * <ul>
 *   <li>클라이언트가 보낸 X-User-Id / X-Internal-Token은 무조건 지운다(위조 방지).</li>
 *   <li>검증된 JWT가 있으면 그 subject를 X-User-Id로 넣는다.</li>
 *   <li>X-Internal-Token(공유 비밀)을 붙여, 뒤쪽 서비스가 Gateway를 거친 요청만 받게 한다.</li>
 * </ul>
 */
@Component
public class IdentityPropagationFilter implements GlobalFilter, Ordered {
    static final String USER_ID_HEADER = "X-User-Id";
    static final String INTERNAL_TOKEN_HEADER = "X-Internal-Token";

    private final String internalToken;

    public IdentityPropagationFilter(@Value("${app.internal-token}") String internalToken) {
        this.internalToken = internalToken;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        return exchange.getPrincipal()
                .filter(JwtAuthenticationToken.class::isInstance)
                .map(principal -> ((JwtAuthenticationToken) principal).getToken().getSubject())
                .map(userId -> rewrite(exchange, userId))
                .defaultIfEmpty(rewrite(exchange, null))
                .flatMap(chain::filter);
    }

    private ServerWebExchange rewrite(ServerWebExchange exchange, String userId) {
        ServerHttpRequest request = exchange.getRequest().mutate()
                .headers(headers -> {
                    headers.remove(USER_ID_HEADER);
                    headers.remove(INTERNAL_TOKEN_HEADER);
                    if (userId != null) {
                        headers.set(USER_ID_HEADER, userId);
                    }
                    headers.set(INTERNAL_TOKEN_HEADER, internalToken);
                })
                .build();
        return exchange.mutate().request(request).build();
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
