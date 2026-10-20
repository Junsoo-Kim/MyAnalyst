package khu_swcon.myanalyst.auth.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import khu_swcon.myanalyst.auth.client.UserServiceClient;
import khu_swcon.myanalyst.auth.client.UserServiceClient.UserServiceUnavailableException;
import khu_swcon.myanalyst.auth.token.SigningKeyProvider;
import khu_swcon.myanalyst.auth.token.TokenService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 로그인/로그아웃/토큰 갱신. 경로와 응답 형식은 세션 시절과 같게 두어 FE의 로그인·로그아웃 코드를 바꾸지 않는다
 * (POST /sessions → {"userid"}, DELETE /sessions → 204). 차이는 서버 세션 대신 토큰 쿠키가 내려간다는 것뿐이다.
 */
@RestController
public class SessionController {

    public record LoginRequest(@NotBlank String userid, @NotBlank String password) {
    }

    private final UserServiceClient userServiceClient;
    private final TokenService tokenService;
    private final SigningKeyProvider keys;
    private final AuthCookies cookies;

    public SessionController(UserServiceClient userServiceClient, TokenService tokenService,
                             SigningKeyProvider keys, AuthCookies cookies) {
        this.userServiceClient = userServiceClient;
        this.tokenService = tokenService;
        this.keys = keys;
        this.cookies = cookies;
    }

    @PostMapping("/sessions")
    public ResponseEntity<?> login(@Valid @RequestBody LoginRequest request) {
        UserServiceClient.Verification verification;
        try {
            verification = userServiceClient.verify(request.userid(), request.password());
        } catch (UserServiceUnavailableException e) {
            // 자격 증명을 확인할 수 없으면 로그인만 실패한다. 이미 발급된 토큰은 Gateway가 계속 받아준다.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("message", "로그인 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해주세요."));
        }
        return switch (verification) {
            case OK -> cookies.withTokens(ResponseEntity.ok(), tokenService.issue(request.userid()))
                    .body(Map.of("userid", request.userid()));
            case UNKNOWN_USER -> ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("message", "사용자 ID가 존재하지 않습니다: " + request.userid()));
            case WRONG_PASSWORD -> ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("message", "비밀번호가 일치하지 않습니다"));
        };
    }

    @DeleteMapping("/sessions")
    public ResponseEntity<Void> logout(@CookieValue(name = AuthCookies.REFRESH, required = false) String refreshToken) {
        tokenService.revoke(refreshToken);
        return cookies.cleared(ResponseEntity.noContent()).build();
    }

    /**
     * access token이 만료되면 FE가 이 경로를 한 번 부르고 원래 요청을 다시 보낸다. refresh token은 쓰는 즉시
     * 새것으로 바뀌므로, 탈취된 refresh token이 한 번 쓰이면 원래 사용자의 다음 갱신이 실패해 드러난다.
     */
    @PostMapping("/auth/refresh")
    public ResponseEntity<?> refresh(@CookieValue(name = AuthCookies.REFRESH, required = false) String refreshToken) {
        return tokenService.rotate(refreshToken)
                .<ResponseEntity<?>>map(tokens -> cookies.withTokens(ResponseEntity.ok(), tokens).body(Map.of("refreshed", true)))
                .orElseGet(() -> cookies.cleared(ResponseEntity.status(HttpStatus.UNAUTHORIZED))
                        .build());
    }

    /** Gateway가 access token 서명을 검증할 공개키. 비공개키는 이 서비스 밖으로 나가지 않는다. */
    @GetMapping("/.well-known/jwks.json")
    public Map<String, Object> jwks() {
        return keys.publicJwkSet().toJSONObject();
    }
}
