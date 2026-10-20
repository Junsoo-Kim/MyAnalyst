package khu_swcon.myanalyst.auth;

import jakarta.servlet.http.HttpSession;

/**
 * 요청의 인증 사용자를 어디서 꺼내는지 아는 유일한 곳.
 * 컨트롤러는 세션 속성을 직접 읽지 않고 이 클래스를 거치므로, 이후 Gateway가 넘겨주는
 * 헤더 방식으로 바꿀 때 auth 모듈만 고치면 된다.
 */
public final class CurrentUser {
    public static final String SESSION_ATTRIBUTE = "userId";

    private CurrentUser() {
    }

    public static String of(HttpSession session) {
        return (String) session.getAttribute(SESSION_ATTRIBUTE);
    }

    public static void signIn(HttpSession session, String userId) {
        session.setAttribute(SESSION_ATTRIBUTE, userId);
    }
}
