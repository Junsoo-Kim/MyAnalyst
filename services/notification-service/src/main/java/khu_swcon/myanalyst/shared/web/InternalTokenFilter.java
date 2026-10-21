package khu_swcon.myanalyst.shared.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Gateway를 거친 요청(X-Internal-Token 일치)만 받는다. 그래야 X-User-Id 헤더를 믿을 수 있다. 헬스체크·지표는 예외다.
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
