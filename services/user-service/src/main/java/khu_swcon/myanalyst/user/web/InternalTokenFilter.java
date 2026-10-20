package khu_swcon.myanalyst.user.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;

/**
 * Gateway나 auth-service를 거친 요청(X-Internal-Token 일치)만 받는다. 이 서비스의 포트가 네트워크에서 열려 있어도
 * 외부에서 직접 가입 API나 내부 자격 증명 확인 API를 부를 수 없게 한다. 헬스체크·지표는 예외다.
 */
@Component
public class InternalTokenFilter extends OncePerRequestFilter {
    private final byte[] expected;

    public InternalTokenFilter(@Value("${app.internal-token}") String internalToken) {
        this.expected = internalToken.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return request.getRequestURI().startsWith("/actuator/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String presented = request.getHeader("X-Internal-Token");
        if (presented == null || !MessageDigest.isEqual(expected, presented.getBytes(StandardCharsets.UTF_8))) {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"message\":\"Requests must come through the API gateway\"}");
            return;
        }
        chain.doFilter(request, response);
    }
}
