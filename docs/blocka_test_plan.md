# Block A silicon test plan

This is the plan for bringing up and characterising MOSAIC-SoC Block A on the
Chipathon 2026 D15 shuttle (GF180MCU, `gf180mcuD`). It covers the board, the
firmware we need to have ready before parts arrive, the order of the tests,
and what to suspect when a step fails.

Every expected value below comes from the shipped netlist or from the RTL. If
the layout is ever re-hardened, re-derive the numbers in §5 and §6.

## 1. What is on the chip

|             |                                                                                                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Layout      | `flow/librelane/experimental/runs/blocka_padframe_def/final/gds`, saved views in `flow/librelane/experimental/runs/blocka_padframe_def`                          |
| Slot        | D15 block A, 1110 × 1110 µm, pads W12 to W22 and N01 to N11                                                                                                      |
| Harts       | Two SERV cores. Hart 0 (TITAN, rv32ic with CSRs) boots from the ROM. Hart 1 (worker, rv32i, no CSRs) is woken by the TDU and starts at `0x4001_0000`             |
| Memory      | 1 KiB boot ROM at `0x2001_0000`, 128 B flip-flop scratchpad at `0x0`, no SRAM. All code executes in place from external SPI flash mapped at `0x4000_0000`        |
| Peripherals | UART at `0x3008_0000` (OpenTitan, FIFOs cut to 4 entries), TDU at `0x200A_0000`, CLINT at `0x200B_0000`, soc_ctrl at `0x2000_0000`                               |
| Not present | JTAG, DMA, PLIC, GPIO, SPI host. The flash interface is read-only                                                                                                |
| Clock       | 20 MHz target. Setup slack +2.199 ns at ss/125 °C/4.5 V and +7.78 ns at tt/25 °C/5.0 V. Hold slack +0.054 ns at ff/−40 °C/5.5 V                                  |
| Supply      | Signed off at 5.0 V, corners 4.5 to 5.5 V. The macro's VDD and VSS land on the DVDD/DVSS pad cells, so the core and our segment of the pad ring share one supply |
| Power       | 150 mW at 20 MHz from LibreLane's default switching activity, about 30 mA at 5 V.                                                                                |

## 2. What we can observe

There is no JTAG. These are the only windows into the part:

1. **`status_o[6:0]` and `status_valid_o`.** These pins show soc_ctrl
   `EXIT_VALUE[6:0]` (`0x2000_0004`) and `EXIT_VALID` (`0x2000_0000`), and
   they follow the registers at all times. Firmware can write a progress code
   to `EXIT_VALUE` without setting `EXIT_VALID`, so the pins show how far a
   run got before it stopped.
2. **UART TX.** This is the only channel with real bandwidth.
3. **The flash bus.** In single-SPI mode, every non-sequential fetch puts
   command `0x03` and a 24-bit address on IO0. A logic analyser with an SPI
   decoder therefore gives you a trace of fetch addresses for both harts.
   Sequential fetches continue the burst without a new command. This trace is
   the closest thing we have to a debugger.
4. **Supply current.**

## 3. Pins and board requirements

| Slot       | Pin                            | Pad cell                     | Board connection                                    | Level in reset |
| ---------- | ------------------------------ | ---------------------------- | --------------------------------------------------- | -------------- |
| W12        | VSS                            | dvss                         | ground                                              |                |
| W13        | `clk_i`                        | in_s (Schmitt)               | oscillator or generator, full swing                 |                |
| W14        | `rst_ni`                       | in_c, **internal pull-down** | supervisor plus push-button, active low             |                |
| W15        | `boot_select_i`                | in_c, no pull                | jumper with pull resistor. 1 = boot from flash      |                |
| W16        | `execute_from_flash_i`         | in_c, no pull                | jumper with pull resistor. Must be 1 to run code    |                |
| W17        | `uart_rx_i`                    | in_c, no pull                | USB-UART TX, plus a 10 kΩ pull-up (UART idles high) |                |
| W18        | `uart_tx_o`                    | bi_t, output, 12 mA          | USB-UART RX                                         | 1              |
| W19        | `spi_flash_sck_o`              | bi_t, output, 12 mA          | flash CLK                                           | 0              |
| W20        | `spi_flash_cs_o`               | bi_t, output, 12 mA          | flash CS#, 10 kΩ pull-up                            | 1              |
| W21        | `spi_flash_sd_io[0]`           | bi_t, bidirectional          | flash DI / IO0                                      | Hi-Z           |
| W22        | `spi_flash_sd_io[1]`           | bi_t, bidirectional          | flash DO / IO1                                      | Hi-Z           |
| N01        | `spi_flash_sd_io[2]`           | bi_t, bidirectional          | flash WP# / IO2, 10 kΩ pull-up                      | Hi-Z           |
| N02        | `spi_flash_sd_io[3]`           | bi_t, bidirectional          | flash HOLD# / IO3, 10 kΩ pull-up                    | Hi-Z           |
| N03        | `status_valid_o`               | bi_t, output, 12 mA          | LED and logic analyser                              | 0              |
| N04 to N10 | `status_o[0]` to `status_o[6]` | bi_t, output, 12 mA          | LEDs and logic analyser                             | 0              |
| N11        | VDD                            | dvdd                         | 5.0 V, current-limited supply with readback         |                |

All outputs run at fast slew (`SL=0`) and 12 mA drive. The pad settings and
the reasons for them are in `flow/librelane/experimental/padframe/pad_settings.md`.

**Board rules:**

1. **Drive every input.** `clk_i`, `boot_select_i`, `execute_from_flash_i`
   and `uart_rx_i` have no pull. A floating CMOS input reads at random and
   draws crossover current.
2. **Give reset a clean edge.** `rst_ni` is a CMOS input, not a Schmitt
   trigger, so a slow RC ramp can chatter. Use a supervisor that holds reset
   low for at least 10 ms after VDD is in range, so the flash is ready before
   the first access. With an open-drain supervisor, use a pull-up of 10 kΩ or
   less to overcome the internal pull-down. The clock must be running when
   reset releases, because the reset synchroniser needs clock edges.
3. **Match the flash to the pad voltage.** The pads swing from 0 to VDD, which
   is 5 V. Two options:
   - A 5 V serial memory that accepts `0xAB` followed by `0x03` with a 24-bit
     address, such as the Microchip 25LC1024 (128 KiB, 20 MHz at 5 V). Check
     its datasheet against the sequence in §5 before committing. It supports
     single SPI only.
   - A 3.3 V SPI NOR of the W25Q class behind level translation. Shift SCK,
     CS# and IO0 down with a 5 V-tolerant buffer powered at 3.3 V (74LVC125),
     and shift IO1 up with a 5 V buffer that has TTL input thresholds
     (74HCT125). Pull WP# and HOLD# up on the flash side, and pull N01 and N02
     up to VDD on the chip side so those inputs do not float. Dual and quad
     modes (T15) need bidirectional translators instead.

   The image needs flash offsets `0x180` to beyond `0x1_0000`, so use at
   least 128 KiB.

4. **Do not program the flash in circuit.** The chip drives SCK low and CS#
   high even while in reset, so an in-circuit programmer would fight its
   12 mA drivers. Socket the flash, or put jumpers in SCK, CS#, IO0 and IO1.
5. **Put a header on all 20 signal pins** for the logic analyser. The flash
   bus is the main debug view.
6. **Decouple VDD close to the pins** and provide a shunt or a supply with
   current readback.

**Equipment:** a 5 V bench supply with current limit, a 20 MHz oscillator and a
function generator that reaches at least 30 MHz, a logic analyser at 100 MS/s
or more with an SPI decoder (sigrok/PulseView), a 100 MHz oscilloscope, a 5 V
TTL USB-UART that reaches 1 Mbaud (for example an FTDI TTL-232R-5V), a flash programmer with a
socket, and if possible a hot-air gun and freeze spray for T16.

## 4. Firmware to prepare before the parts arrive

Two images exist today. The rest need writing.

| Image      | State                                  | What it does                                                                                                                                                                                                                                                                                         |
| ---------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `generic`  | exists, `tb/mosaic_soc/run_generic.sh` | Hart 0 wakes hart 1 through the TDU, each writes its sentinel, hart 0 exits with 0                                                                                                                                                                                                                   |
| `uart`     | exists, `tb/mosaic_soc/run_uart.sh`    | Checks the TX FIFO depth is 4, sends `MOSAIC BLOCK A UART OK` with polling, checks RX through the UART's internal loopback, exits with 0                                                                                                                                                             |
| `selftest` | **to write**                           | One image that runs phases in order and writes the phase number to `EXIT_VALUE` as it starts each one: scratchpad march test, checksum of a known flash table, TDU wake of hart 1, CLINT `mtime` advancing, UART banner. It exits with 0 on pass, or sets `EXIT_VALID` with the failing phase number |
| `echo`     | **to write**                           | Echoes every byte received on UART RX, for T7                                                                                                                                                                                                                                                        |
| `spimode`  | **to write**, stretch                  | Switches spimemio to dual, then quad, through its config register, reruns the flash checksum and reports the cycle count. Quad needs the flash's QE bit set beforehand with the programmer                                                                                                           |

**Baud rate.** The OpenTitan UART divides as `baud = NCO × f_clk / 2^20`.
`run_uart.sh` fixes `NCO = 2^20 / 20` to match the testbench's UART model, so
the baud is the core clock divided by 20: 1 Mbaud at 20 MHz, 0.0015% slow. An
FT232R adapter receives 1 Mbaud exactly, so the `uart` image can go on
silicon as it is, with the same bits that passed simulation. Build `selftest`
and `echo` with the same NCO so the RTL simulation can check their output
byte for byte. If you need 115200, the NCO is 6040, but the testbench's UART
model then no longer decodes the output, so GLS checks only the exit status.
The baud scales with the clock, so the shmoo (T13) reads only the status pins.

Rules for every image:

- Use RV32I and Zicsr only, in the style of `prog_generic/generic.S`. The
  worker has no CSRs.
- Each image must pass the full-SoC RTL simulation, and then GLS on the
  shipped netlist, before anyone loads it into a flash on a board. Record its
  GLS cycle count as the golden value for §6:

  ```sh
  GLS_RUN=$PWD/flow/librelane/experimental/runs/blocka_padframe_def \
  GLS_TOP=mosaic_block_a_padwrap \
  GLS_POWERUP_INIT=gls_powerup_init_padwrap.svh \
  GLS_FIRMWARE=<image.hex> ./tb/gls/run_gls.sh
  ```

- The simulation hex files are flash-relative Verilog hex: `@` records are
  offsets from flash address 0. Convert them to a binary for the programmer,
  filling gaps with `0xFF`:

  ```python
  import sys
  img, addr = bytearray(b"\xff" * 0x20000), 0
  for line in open(sys.argv[1]):
      for tok in line.split():
          if tok.startswith("@"): addr = int(tok[1:], 16)
          else: img[addr] = int(tok, 16); addr += 1
  open(sys.argv[2], "wb").write(img)
  ```

## 5. The expected boot sequence

This is the reference that T3 to T5 compare against.

1. Reset releases and hart 0 runs the ROM. SERV is bit-serial and takes tens
   of cycles per instruction.
2. The ROM reads `boot_select` (soc_ctrl `0x2000_0008`), which follows the pin
   live. On 0 it jumps back to the start of the ROM and reads the pin again,
   with the flash idle. On 1 it continues.
3. The ROM reads `use_spimemio`, which follows `execute_from_flash_i`. On 0 it
   takes the copy-from-flash path, which needs the SPI host this part does not
   have. The access returns 0 and the ROM spins forever with the flash idle.
   On 1 it writes `START_SPIMEM`.
4. spimemio sends `0xFF`, then `0xAB`, then `0x03 00 01 80`, and streams data
   from there. SCK runs at half the core clock, 10 MHz at 20 MHz.
5. Hart 0 runs from `0x4000_0180`. When it wakes hart 1, a `0x03 01 00 00`
   command appears on the bus.
6. The firmware writes `EXIT_VALUE` and then `EXIT_VALID`. With `generic`, GLS
   on the shipped netlist sees `status_valid_o` 12,404 cycles after reset
   releases, which is 620 µs at 20 MHz, with `status_o` = 0.

## 6. Tests

Run the tests in order. Each one depends on the ones before it. Label every
part, and record the results per part (§8).

### Phase A: unpowered and static

| ID  | Test                        | Procedure                                                                                                           | Pass                                                                               |
| --- | --------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| T0  | Continuity                  | Unpowered. Measure VDD to VSS resistance, and check that no signal pin is shorted to its neighbours or to the rails | No shorts. Record VDD to VSS resistance as the baseline for every later part       |
| T1  | Power-up in reset, no clock | Hold `rst_ni` low and stop the clock. Ramp VDD to 5.0 V with a 100 mA limit                                         | IDD is small and stable, and the outputs sit at the reset levels in §3. Record IDD |
| T2  | Clock in reset              | Same as T1, then start a 20 MHz clock                                                                               | IDD rises by the clock tree's share, and the outputs do not move. Record IDD       |
| T2b | Reset pull-down             | Disconnect the reset driver                                                                                         | The part stays in reset, with outputs at their reset levels                        |

### Phase B: boot

| ID  | Test                   | Procedure                                                                                                                                    | Pass                                                                                                                                                                  |
| --- | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T3  | Boot pin parks the ROM | `boot_select_i` = 0, `execute_from_flash_i` = 1, flash holds `generic`. Release reset, wait 1 s, then set `boot_select_i` = 1                | Flash bus idle while the pin is 0. Moving it to 1 starts the sequence in §5 without a reset                                                                           |
| T4  | First boot             | `boot_select_i` = 1, `execute_from_flash_i` = 1, flash holds `generic`. Release reset with the analyser on the flash bus and the status pins | `0xFF`, `0xAB`, `0x03 00 01 80` in that order. A `0x03 01 00 00` fetch shows hart 1 woke. `status_valid_o` rises with `status_o` = 0, about 12,404 cycles after reset |
| T5  | XIP pin                | `execute_from_flash_i` = 0, then release reset                                                                                               | No flash activity and `status_valid_o` stays 0. This is the expected hang from §5, step 3. It shows the pin reaches soc_ctrl                                          |

### Phase C: function

| ID  | Test             | Procedure                                                                                                | Pass                                                                |
| --- | ---------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| T6  | UART TX          | Flash `uart`. Host terminal at 1,000,000 baud 8N1 (core clock / 20)                                      | `MOSAIC BLOCK A UART OK` arrives intact, and the image exits with 0 |
| T7  | UART RX          | Flash `echo`. Send 1 kB of random bytes from the host, then repeat with the RX/TX pins jumpered together | Every byte comes back unchanged                                     |
| T8  | Self-test        | Flash `selftest`                                                                                         | Exits with 0. On a failure, the status pins name the phase          |
| T9  | Flash data loads | Covered by `selftest`'s checksum phase. It also guards bug 31, where loads from the flash window hung    | Checksum matches                                                    |
| T10 | Worker wake      | Covered by `selftest`'s TDU phase and by T4                                                              | Hart 1's sentinel is set, and its fetch appears on the bus          |
| T11 | Timer            | `selftest` prints `mtime` at two UART messages. Compare the difference with the host's clock             | `mtime` rate matches the clock source within its tolerance          |

### Phase D: robustness and characterisation

| ID  | Test                        | Procedure                                                                                                               | Pass                                                                                                                                                                                                                         |
| --- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T12 | Reset and power cycling     | 1,000 reset pulses at random points during a run. Then 100 full power cycles                                            | Every run ends in the same exit with the same cycle count. A failure after a power cycle that never happens after a reset points at a flop without reset (§4)                                                                |
| T13 | Shmoo                       | `selftest`, VDD at 4.5, 5.0 and 5.5 V, clock from 1 MHz to the first failure in 1 MHz steps, then finer around the edge | 20 MHz passes at every VDD. Record the highest passing frequency per VDD. STA predicts about 20.9 MHz at the slow corner and about 23.7 MHz typical, but the SDC's I/O delays scale with the period, so treat those as rough |
| T14 | Power                       | Measure IDD in reset and running, at 5, 10, 15 and 20 MHz                                                               | IDD rises linearly with frequency. Report energy per cycle as the slope, and leakage plus static current as the intercept. Compare with the 30 mA estimate                                                                   |
| T15 | Dual and quad SPI (stretch) | `spimode`, on a SPI NOR with QE set                                                                                     | Checksum still matches, and the cycle count drops                                                                                                                                                                            |
| T16 | Temperature (stretch)       | Repeat T8 at 20 MHz and at 1 MHz while heating with hot air, then cooling with freeze spray                             | Passes at both frequencies. A failure that persists at 1 MHz when cold is a hold failure, because the hold slack is 0.054 ns at the fast corner                                                                              |

## 7. When a step fails

| Symptom                                           | Suspect first                                                                                                                                                                                         |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| High IDD in T1 with no clock                      | A floating input (rule 1), a short (T0), or a supply or pad problem. Remove inputs one at a time                                                                                                      |
| Outputs at wrong levels in reset                  | Pad wiring or reset distribution. Compare against §3 pin by pin                                                                                                                                       |
| No flash activity in T4                           | The boot or XIP pin was not 1 (T3, T5), the clock was not running when reset released, or the ROM did not execute. Check that `status_o` is 0 and IDD rises after reset                               |
| `0xFF` and `0xAB` appear but data reads are wrong | The flash level shifter, IO1 direction, or the flash's power-up time. Probe IO1 with the scope                                                                                                        |
| Hart 0 runs, but hart 1's fetch never appears     | The TDU wake path. Run `selftest` to get the phase number                                                                                                                                             |
| Fails at every frequency, including 1 MHz         | Not setup timing. Suspect hold (T16), reset, or power-up state (T12)                                                                                                                                  |
| Passes at low frequency, fails above some point   | Setup timing, or the off-chip flash read path. The analyser shows which: a wrong fetch address means internal logic failed, while a correct address followed by a wrong flow means bad data came back |
| UART output is garbled                            | The host is not at core clock / 20, or the clock is not the frequency you think it is. Measure it with the scope                                                                                      |

## 8. Recording results

Silicon Results not yet available

| Part | Test | VDD (V) | f (MHz) | Temp | IDD (mA) | Result | Capture |
| ---- | ---- | ------- | ------- | ---- | -------- | ------ | ------- |
|      |      |         |         |      |          |        |         |
