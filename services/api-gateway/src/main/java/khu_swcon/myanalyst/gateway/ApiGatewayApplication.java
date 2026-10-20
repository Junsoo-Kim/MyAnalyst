package khu_swcon.myanalyst.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * api-gateway: 외부에서 들어오는 유일한 입구.
 * <ul>
 *   <li>access token(JWT, RS256)을 auth-service의 JWKS 공개키로 직접 검증한다 — 요청마다 auth-service를 부르지 않는다.</li>
 *   <li>검증한 사용자 ID를 X-User-Id 헤더로 넘긴다. 클라이언트가 보낸 X-User-Id는 지운다.</li>
 *   <li>CORS, 로그인 시도 rate limit(Redis)을 맡는다.</li>
 * </ul>
 */
@SpringBootApplication
public class ApiGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiGatewayApplication.class, args);
    }
}
