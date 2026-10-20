package khu_swcon.myanalyst.user;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * user-service: 회원 가입과 자격 증명 확인. Users 테이블(비밀번호 해시 포함)의 소유자다.
 * 토큰은 발급하지 않는다 — 로그인 시 auth-service가 내부 API로 자격 증명만 확인받는다.
 */
@SpringBootApplication
public class UserServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserServiceApplication.class, args);
    }
}
