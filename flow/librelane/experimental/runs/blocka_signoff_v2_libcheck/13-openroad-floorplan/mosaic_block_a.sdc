###############################################################################
# Created by write_sdc
###############################################################################
current_design mosaic_block_a
###############################################################################
# Timing Constraints
###############################################################################
create_clock -name clk_i -period 100.0000 [get_ports {clk_i}]
set_clock_transition 0.1500 [get_clocks {clk_i}]
set_clock_uncertainty 0.2500 clk_i
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {boot_select_i}]
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {execute_from_flash_i}]
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {rst_ni}]
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[0]}]
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[1]}]
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[2]}]
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[3]}]
set_input_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {uart_rx_i}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_cs_o}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sck_o}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[0]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[1]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[2]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {spi_flash_sd_io[3]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_o[0]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_o[1]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_o[2]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_o[3]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_o[4]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_o[5]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_o[6]}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {status_valid_o}]
set_output_delay 20.0000 -clock [get_clocks {clk_i}] -add_delay [get_ports {uart_tx_o}]
###############################################################################
# Environment
###############################################################################
set_load -pin_load 0.0729 [get_ports {spi_flash_cs_o}]
set_load -pin_load 0.0729 [get_ports {spi_flash_sck_o}]
set_load -pin_load 0.0729 [get_ports {status_valid_o}]
set_load -pin_load 0.0729 [get_ports {uart_tx_o}]
set_load -pin_load 0.0729 [get_ports {spi_flash_sd_io[3]}]
set_load -pin_load 0.0729 [get_ports {spi_flash_sd_io[2]}]
set_load -pin_load 0.0729 [get_ports {spi_flash_sd_io[1]}]
set_load -pin_load 0.0729 [get_ports {spi_flash_sd_io[0]}]
set_load -pin_load 0.0729 [get_ports {status_o[6]}]
set_load -pin_load 0.0729 [get_ports {status_o[5]}]
set_load -pin_load 0.0729 [get_ports {status_o[4]}]
set_load -pin_load 0.0729 [get_ports {status_o[3]}]
set_load -pin_load 0.0729 [get_ports {status_o[2]}]
set_load -pin_load 0.0729 [get_ports {status_o[1]}]
set_load -pin_load 0.0729 [get_ports {status_o[0]}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {boot_select_i}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_4 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {clk_i}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {execute_from_flash_i}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {rst_ni}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uart_rx_i}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {spi_flash_sd_io[3]}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {spi_flash_sd_io[2]}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {spi_flash_sd_io[1]}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {spi_flash_sd_io[0]}]
###############################################################################
# Design Rules
###############################################################################
set_max_transition 3.0000 [current_design]
set_max_capacitance 0.2000 [current_design]
set_max_fanout 10.0000 [current_design]
