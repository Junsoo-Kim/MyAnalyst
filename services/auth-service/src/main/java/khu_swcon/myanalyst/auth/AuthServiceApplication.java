package khu_swcon.myanalyst.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * auth-service: 로그인(자격 증명은 user-service가 확인), access JWT 발급, refresh 토큰 교체, 로그아웃, JWKS 공개.
 * 요청마다 토큰을 검증하는 일은 하지 않는다 — Gateway가 JWKS 공개키로 직접 검증하므로, 이 서비스가 내려가도
 * 이미 로그인한 사용자의 요청은 계속 처리된다.
 */
@SpringBootApplication
public class AuthServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthServiceApplication.class, args);
    }
}
