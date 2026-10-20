package khu_swcon.myanalyst.auth;

import jakarta.servlet.http.HttpServletRequest;

/**
 * 요청의 인증 사용자를 어디서 꺼내는지 아는 유일한 곳.
 *
 * <p>MSA 4단계부터 BE는 직접 인증하지 않는다. api-gateway가 JWT를 검증한 뒤 그 subject를 {@value #USER_ID_HEADER}
 * 헤더로 넘기고, 클라이언트가 보낸 같은 이름의 헤더는 지운다. 이 헤더는 Gateway를 거친 요청에서만 믿는다
 * ({@code GatewayIdentityInterceptor}가 내부 토큰으로 확인한다).
 */
public final class CurrentUser {
    public static final String USER_ID_HEADER = "X-User-Id";

    private CurrentUser() {
    }

    public static String of(HttpServletRequest request) {
        return request.getHeader(USER_ID_HEADER);
    }
}
