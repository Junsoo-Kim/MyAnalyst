package khu_swcon.myanalyst.service;

import khu_swcon.myanalyst.dto.UserDto;
import khu_swcon.myanalyst.entity.User;
import khu_swcon.myanalyst.exception.InvalidPasswordException;
import khu_swcon.myanalyst.exception.UserNotFoundException;
import khu_swcon.myanalyst.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.security.crypto.password.PasswordEncoder;

@Service
public class UserService {
    
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    
    @Autowired
    public UserService(UserRepository userRepository, PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }
    
    @Transactional
    public User registerUser(UserDto userDto) {
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
        return userRepository.save(user);
    }
    
    @Transactional
    public void login(UserDto userDto) {
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
}
