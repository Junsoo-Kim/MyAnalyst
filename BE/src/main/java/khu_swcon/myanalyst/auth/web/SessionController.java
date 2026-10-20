package khu_swcon.myanalyst.auth.web;

import khu_swcon.myanalyst.auth.CurrentUser;
import khu_swcon.myanalyst.user.InvalidPasswordException;
import khu_swcon.myanalyst.user.UserDto;
import khu_swcon.myanalyst.user.UserNotFoundException;
import khu_swcon.myanalyst.user.UserService;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    private final UserService userService;

    public SessionController(UserService userService) {
        this.userService = userService;
    }

    @PostMapping("/sessions")
    public ResponseEntity<?> login(@Valid @RequestBody UserDto userDto, HttpSession session) {
        try {
            userService.authenticate(userDto);
            CurrentUser.signIn(session, userDto.getUserid());
            return ResponseEntity.ok(java.util.Map.of("userid", userDto.getUserid()));
        } catch (UserNotFoundException e) {
            return new ResponseEntity<>(e.getMessage(), HttpStatus.UNAUTHORIZED);
        } catch (InvalidPasswordException e) {
            return new ResponseEntity<>(e.getMessage(), HttpStatus.UNAUTHORIZED);
        } catch (Exception e) {
            return new ResponseEntity<>("로그인 중 오류가 발생했습니다", HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @DeleteMapping("/sessions")
    public ResponseEntity<Void> logout(HttpSession session) {
        session.invalidate();
        return ResponseEntity.noContent().build();
    }
}
