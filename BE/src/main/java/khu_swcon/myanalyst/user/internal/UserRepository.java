package khu_swcon.myanalyst.user.internal;

import khu_swcon.myanalyst.user.internal.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface UserRepository extends JpaRepository<User, String> {
    boolean existsByUserid(String userid);
    Optional<User> findByUserid(String userid);
}
