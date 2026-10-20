package khu_swcon.myanalyst.dictionary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication(scanBasePackages = "khu_swcon.myanalyst")
@EnableScheduling
public class DictionaryServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(DictionaryServiceApplication.class, args);
    }
}
