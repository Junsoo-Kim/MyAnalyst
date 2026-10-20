package khu_swcon.myanalyst.user;

import khu_swcon.myanalyst.user.internal.User;
import khu_swcon.myanalyst.user.internal.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * 사용자 모듈의 공개 API. 다른 모듈은 User 엔티티가 아니라 이 클래스를 통해서만 사용자에 접근한다.
 */
@Service
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public UserService(UserRepository userRepository, PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @Transactional
    public void registerUser(UserDto userDto) {
        // Check if user already exists
        if (userRepository.existsByUserid(userDto.getUserid())) {
            throw new RuntimeException("User ID already exists");
        }

        // Create new user
        User user = User.builder()
                .userid(userDto.getUserid())
                .password(passwordEncoder.encode(userDto.getPassword()))
                .build();

        // Save user to database
        userRepository.save(user);
    }

    @Transactional
    public void authenticate(UserDto userDto) {
        // 1. 사용자 ID 검증
        User user = userRepository.findByUserid(userDto.getUserid())
                .orElseThrow(() -> new UserNotFoundException("사용자 ID가 존재하지 않습니다: " + userDto.getUserid()));

        // 2. 비밀번호 검증
        if (!passwordEncoder.matches(userDto.getPassword(), user.getPassword())) {
            if (user.getPassword().equals(userDto.getPassword())) {
                user.setPassword(passwordEncoder.encode(userDto.getPassword()));
                return;
            }
            throw new InvalidPasswordException("비밀번호가 일치하지 않습니다");
        }

        // 로그인 성공, 특별한 반환값 없음
    }

    @Transactional(readOnly = true)
    public boolean exists(String userId) {
        return userRepository.existsByUserid(userId);
    }
}
