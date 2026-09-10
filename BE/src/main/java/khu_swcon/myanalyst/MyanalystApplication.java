package khu_swcon.myanalyst;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class MyanalystApplication {

	public static void main(String[] args) {
		SpringApplication.run(MyanalystApplication.class, args);
	}
}
