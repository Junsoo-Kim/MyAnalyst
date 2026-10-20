package khu_swcon.myanalyst.auth.web;

import khu_swcon.myanalyst.auth.token.TokenService.IssuedTokens;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 토큰을 HttpOnly 쿠키로 내려준다. FE의 EventSource(SSE)와 차트 &lt;img&gt;는 Authorization 헤더를 실을 수 없어서
 * 헤더 방식으로는 인증이 안 된다. HttpOnly라 스크립트(XSS)로는 읽을 수 없고, SameSite=Lax로 다른 사이트에서
 * 시작된 요청에는 붙지 않는다. refresh token은 갱신 경로(/auth)로만 전송되게 Path를 좁힌다.
 */
@Component
public class AuthCookies {
    public static final String ACCESS = "access_token";
    public static final String REFRESH = "refresh_token";
    private static final String REFRESH_PATH = "/auth";

    private final boolean secure;

    public AuthCookies(@Value("${app.cookies.secure:false}") boolean secure) {
        this.secure = secure;
    }

    public ResponseEntity.BodyBuilder withTokens(ResponseEntity.BodyBuilder response, IssuedTokens tokens) {
        return response
                .header(HttpHeaders.SET_COOKIE, cookie(ACCESS, tokens.accessToken(), "/", tokens.accessTtl()).toString())
                .header(HttpHeaders.SET_COOKIE, cookie(REFRESH, tokens.refreshToken(), REFRESH_PATH, tokens.refreshTtl()).toString());
    }

    public ResponseEntity.HeadersBuilder<?> cleared(ResponseEntity.HeadersBuilder<?> response) {
        return response
                .header(HttpHeaders.SET_COOKIE, cookie(ACCESS, "", "/", Duration.ZERO).toString())
                .header(HttpHeaders.SET_COOKIE, cookie(REFRESH, "", REFRESH_PATH, Duration.ZERO).toString());
    }

    private ResponseCookie cookie(String name, String value, String path, Duration maxAge) {
        return ResponseCookie.from(name, value)
                .httpOnly(true)
                .secure(secure)
                .sameSite("Lax")
                .path(path)
                .maxAge(maxAge)
                .build();
    }
}
