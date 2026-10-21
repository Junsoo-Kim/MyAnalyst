package khu_swcon.myanalyst.auth.internal;

import khu_swcon.myanalyst.auth.CurrentUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Gateway를 거친, 인증된 요청만 통과시킨다.
 * <ul>
 *   <li>X-Internal-Token이 Gateway와 공유한 값과 다르면 403 — BE 포트에 직접 붙어 X-User-Id를 위조하는 것을 막는다.</li>
 *   <li>X-User-Id가 없으면 401 — Gateway가 JWT를 검증하지 못한 요청이다(정상 경로에서는 Gateway에서 이미 걸러진다).</li>
 * </ul>
 * 공유 비밀은 네트워크 격리(외부에는 Gateway만 노출)를 보완하는 장치다. 운영에서는 mTLS 같은 서비스 간 인증으로 대체할 수 있다.
 */
@Component
public class GatewayIdentityInterceptor implements HandlerInterceptor {
    private final byte[] internalToken;

    public GatewayIdentityInterceptor(@Value("${app.internal-token}") String internalToken) {
        this.internalToken = internalToken.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if (HttpMethod.OPTIONS.matches(request.getMethod()) || "/error".equals(request.getRequestURI())) {
            return true;
        }
        String presented = request.getHeader("X-Internal-Token");
        if (presented == null || !MessageDigest.isEqual(internalToken, presented.getBytes(StandardCharsets.UTF_8))) {
            return reject(response, HttpStatus.FORBIDDEN, "Requests must come through the API gateway");
        }
        String userId = CurrentUser.of(request);
        if (userId == null || userId.isBlank()) {
            return reject(response, HttpStatus.UNAUTHORIZED, "Authentication is required");
        }
        return true;
    }

    private static boolean reject(HttpServletResponse response, HttpStatus status, String message) throws Exception {
        response.setStatus(status.value());
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"message\":\"" + message + "\"}");
        return false;
    }
}
