module blinky (
    input  clk_i,
    input  rst_i,
    output led_o
);
    \logic::blinky::blinky  u_blinky (
        .clk_i(clk_i),
        .rst_i(rst_i),
        .output__(led_o)
    );
endmodule
