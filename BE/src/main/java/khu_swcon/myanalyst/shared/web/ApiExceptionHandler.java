package khu_swcon.myanalyst.shared.web;

import khu_swcon.myanalyst.shared.ApiException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

/**
 * ApiException을 그 상태 코드로 응답한다. 대부분의 컨트롤러는 직접 잡아 처리하지만, /report-jobs 컨트롤러는
 * 잡지 않아서 "다른 사용자의 Job"(404)이 500으로 나가고 있었다(4단계 검증 중 발견).
 */
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, String>> handle(ApiException exception) {
        return ResponseEntity.status(exception.getStatus()).body(Map.of("message", exception.getMessage()));
    }
}
