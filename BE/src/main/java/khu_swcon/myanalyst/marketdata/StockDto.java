package khu_swcon.myanalyst.marketdata;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class StockDto {
    private String retrieved_at;
    private String data_timestamp_info;
    private String company_name;
    private String stock_code;
    private String market_type;
    private String item_main_url;
    private String current_price;
    private String price_change;
    private String change_rate;
    private String yesterday_close;
    private String open_price;
    private String high_price;
    private String low_price;
    private String upper_limit_price;
    private String lower_limit_price;
    private String volume;
    private String volume_value;
    private String market_cap;
    private String market_cap_rank;
    private String shares_outstanding;
    private String foreign_ownership_ratio;
    private String fifty_two_week_high;
    private String fifty_two_week_low;
    private String per_info;
    private String eps_info;
    private String estimated_per_info;
    private String estimated_eps_info;
    private String pbr_info;
    private String bps_info;
    private String dividend_yield_info;
    private String industry_per_info;
}
