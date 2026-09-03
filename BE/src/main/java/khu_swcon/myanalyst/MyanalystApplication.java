package khu_swcon.myanalyst;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

// CORS 설정은 config.WebConfig 한 곳에서만 관리합니다 (중복 Bean 정의 제거).
@SpringBootApplication
public class MyanalystApplication {

	public static void main(String[] args) {
		SpringApplication.run(MyanalystApplication.class, args);
	}
}
