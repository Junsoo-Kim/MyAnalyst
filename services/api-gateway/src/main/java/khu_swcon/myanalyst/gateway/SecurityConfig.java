package khu_swcon.myanalyst.gateway;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpCookie;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.List;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {
    static final String ACCESS_TOKEN_COOKIE = "access_token";

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // 토큰은 HttpOnly + SameSite=Lax 쿠키다. 다른 사이트에서 시작한 POST/DELETE에는 쿠키가 붙지 않으므로
                // 별도 CSRF 토큰은 두지 않는다(같은 사이트의 다른 출처는 아래 CORS 허용 목록으로 제한한다).
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.OPTIONS).permitAll()
                        .pathMatchers(HttpMethod.POST, "/sessions", "/users", "/auth/refresh").permitAll()
                        .pathMatchers(HttpMethod.DELETE, "/sessions").permitAll()
                        .pathMatchers("/actuator/health/**", "/actuator/prometheus").permitAll()
                        // 서비스 간 내부 API는 밖에서 부를 수 없다.
                        .pathMatchers("/internal/**").denyAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .bearerTokenConverter(bearerTokenFromHeaderOrCookie())
                        .jwt(jwt -> { }))
                .build();
    }

    /**
     * 서명(JWKS 공개키), 만료, 발급자(auth-service)를 확인한다.
     * 기본 검증기는 만료에 60초의 시계 오차를 허용해 15분 토큰이 사실상 16분 유효했다(4단계 검증 중 확인).
     * 같은 Docker/VPC 안의 서비스끼리라 시계 차이가 작으므로 몇 초로 줄인다.
     */
    @Bean
    public ReactiveJwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.jwt.issuer}") String issuer,
            @Value("${app.jwt.clock-skew:5s}") Duration clockSkew) {
        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri).build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(clockSkew), new JwtIssuerValidator(issuer)));
        return decoder;
    }

    /**
     * Authorization: Bearer 헤더가 있으면 그것을, 없으면 access_token 쿠키를 쓴다. 브라우저의 EventSource(SSE)와
     * &lt;img&gt;는 헤더를 붙일 수 없어서 쿠키가 필요하고, 스크립트나 다른 서비스는 헤더를 쓸 수 있다.
     */
    private ServerAuthenticationConverter bearerTokenFromHeaderOrCookie() {
        ServerBearerTokenAuthenticationConverter header = new ServerBearerTokenAuthenticationConverter();
        return exchange -> header.convert(exchange)
                .switchIfEmpty(Mono.defer(() -> {
                    HttpCookie cookie = exchange.getRequest().getCookies().getFirst(ACCESS_TOKEN_COOKIE);
                    return cookie == null || cookie.getValue().isBlank()
                            ? Mono.empty()
                            : Mono.just(new BearerTokenAuthenticationToken(cookie.getValue()));
                }));
    }

    /**
     * CORS를 Security보다 앞에서 처리한다. 그래야 인증 실패(401) 응답에도 CORS 헤더가 붙어, 브라우저가 401을
     * CORS 오류로 가리지 않고 FE가 토큰 갱신을 시도할 수 있다.
     */
    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    public CorsWebFilter corsWebFilter(@Value("${app.cors.allowed-origins}") List<String> allowedOrigins) {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(allowedOrigins);
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        config.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return new CorsWebFilter(source);
    }
}
