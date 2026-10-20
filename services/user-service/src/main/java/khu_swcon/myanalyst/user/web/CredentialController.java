package khu_swcon.myanalyst.user.web;

import jakarta.validation.Valid;
import khu_swcon.myanalyst.user.InvalidPasswordException;
import khu_swcon.myanalyst.user.UserDto;
import khu_swcon.myanalyst.user.UserNotFoundException;
import khu_swcon.myanalyst.user.UserService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * auth-service만 부르는 내부 API. Gateway는 /internal/** 을 외부로 라우팅하지 않는다.
 * 비밀번호 해시는 이 서비스 밖으로 나가지 않고, 확인 결과(누구인지)만 돌려준다.
 */
@RestController
public class CredentialController {

    private final UserService userService;

    public CredentialController(UserService userService) {
        this.userService = userService;
    }

    @PostMapping("/internal/credentials/verify")
    public ResponseEntity<?> verify(@Valid @RequestBody UserDto userDto) {
        try {
            userService.authenticate(userDto);
            return ResponseEntity.ok(Map.of("userid", userDto.getUserid()));
        } catch (UserNotFoundException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("message", e.getMessage()));
        } catch (InvalidPasswordException e) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("message", e.getMessage()));
        }
    }
}
