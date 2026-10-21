package khu_swcon.myanalyst.dictionary.web;

import khu_swcon.myanalyst.shared.web.CurrentUser;
import khu_swcon.myanalyst.dictionary.DictionaryService;
import khu_swcon.myanalyst.dictionary.DomainSpecificTermDto;
import khu_swcon.myanalyst.shared.ApiException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
public class DictionaryController {

    private final DictionaryService dictionaryService;

    public DictionaryController(DictionaryService dictionaryService) {
        this.dictionaryService = dictionaryService;
    }

    /**
     * 리포트 ID로 사전 용어 목록 조회
     *
     * @param reportId 리포트 ID
     * @return 도메인 특화 용어 목록
     */
    @GetMapping("/reports/{reportId}/dictionary")
    public ResponseEntity<?> getDictionaryByReportId(@PathVariable Integer reportId, HttpServletRequest request) {
        try {
            List<DomainSpecificTermDto> terms = dictionaryService.getDictionaryByReportId(reportId, CurrentUser.of(request));
            return new ResponseEntity<>(terms, HttpStatus.OK);
        } catch (ApiException e) {
            return new ResponseEntity<>(e.getMessage(), e.getStatus());
        } catch (Exception e) {
            return new ResponseEntity<>("사전 용어 조회 중 오류가 발생했습니다: " + e.getMessage(),
                    HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}
