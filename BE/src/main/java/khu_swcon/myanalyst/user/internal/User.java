package khu_swcon.myanalyst.user.internal;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

@Entity
@Table(name = "Users") // 실제 테이블명 Users에 매핑
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class User {

    @Id
    @Column(name = "userid", length = 20)
    private String userid;

    // BCrypt hashes are 60 characters; leave room for future password encoders.
    @Column(name = "password", nullable = false, length = 255)
    private String password;
}
