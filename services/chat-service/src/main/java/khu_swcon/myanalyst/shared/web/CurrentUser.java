package khu_swcon.myanalyst.shared.web;

import jakarta.servlet.http.HttpServletRequest;

/**
 * api-gateway가 JWT를 검증한 뒤 넘기는 사용자 ID. 클라이언트가 보낸 같은 이름의 헤더는 Gateway가 지우고,
 * Gateway를 거치지 않은 요청은 {@link InternalTokenFilter}가 막으므로 이 헤더를 믿을 수 있다.
 */
public final class CurrentUser {
    public static final String USER_ID_HEADER = "X-User-Id";

    private CurrentUser() {
    }

    public static String of(HttpServletRequest request) {
        return request.getHeader(USER_ID_HEADER);
    }
}
