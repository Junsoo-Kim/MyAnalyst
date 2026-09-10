package khu_swcon.myanalyst.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class RequestTraceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String incomingTraceId = request.getHeader("X-Trace-Id");
        TraceContext.bind(incomingTraceId == null || incomingTraceId.isBlank()
                ? TraceContext.currentTraceId() : incomingTraceId);
        try {
            response.setHeader("X-Trace-Id", TraceContext.currentTraceId());
            filterChain.doFilter(request, response);
        } finally {
            TraceContext.clear();
        }
    }
}
