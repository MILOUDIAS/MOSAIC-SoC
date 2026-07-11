// Copyright 2026 MOSAIC-SoC Contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

/**
 * @file titan_main.c
 * @brief TITAN (cv32e20) orchestrator firmware for MOSAIC-SoC.
 *
 * Demonstrates the full TDU programming model:
 *   1. System initialization
 *   2. TDU configuration (scheduling mode, wake mask)
 *   3. Worker core wake-up via TDU
 *   4. Task dispatch to heterogeneous workers
 *   5. Completion monitoring via shared-memory sentinels
 *   6. Test exit signaling
 *
 * Architecture: cv32e20 (RV32E/M/C) — 16 registers, hardware M-extension.
 * Boot address: 0x180 (set by boot ROM / soc_ctrl).
 *
 * @see hw/tdu/rtl/tdu.sv — TDU implementation
 * @see hw/tdu/rtl/tdu_pkg.sv — register map and task descriptor format
 * @see tb/mosaic_soc/prog/start.S — original bare-metal demo (assembly)
 */

#include "tdu.h"

/** Sentinel value written by TITAN to prove it executed. */
#define SENTINEL_TITAN_VAL  0xC0FFEE00u

/** Sentinel value written by ATLAS workers. */
#define SENTINEL_ATLAS_VAL  0xA71A5000u

/** Sentinel value written by NANO workers. */
#define SENTINEL_NANO_VAL   0x4E414E00u

/**
 * Number of ATLAS (FazyRV) worker cores in the PoC configuration.
 * PoC config: 2 ATLAS (fazyrv, hart 1-2).
 */
#define NUM_ATLAS 2

/**
 * Number of NANO (SERV) worker cores in the PoC configuration.
 * PoC config: 4 NANO (serv, hart 3-6).
 */
#define NUM_NANO  4

/** Total number of worker cores (ATLAS + NANO). */
#define NUM_WORKERS (NUM_ATLAS + NUM_NANO)

/** Task ID for sensor-polling tasks (dispatched to NANO). */
#define TASK_ID_SENSOR_POLL  0x0001u

/** Task ID for signal-processing tasks (dispatched to ATLAS). */
#define TASK_ID_SIGNAL_PROC  0x0002u

/** Task ID for aggregation tasks. */
#define TASK_ID_AGGREGATE    0x0003u

/** Maximum polling iterations before timeout. */
#define POLL_TIMEOUT 1000000u

/**
 * Population count (number of set bits) for RV32I.
 *
 * RV32I has no popcount instruction, and linking __popcountsi2 would
 * require libgcc. This avoids the library dependency.
 *
 * @param x 32-bit value.
 * @return Number of set bits.
 */
static inline uint32_t popcount32(uint32_t x) {
    x = x - ((x >> 1) & 0x55555555u);
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    return (((x + (x >> 4)) & 0x0F0F0F0Fu) * 0x01010101u) >> 24;
}

/** MMIO region handle for shared sentinel memory. */
static mmio_region_t sentinel_region = {0};

/**
 * Initialize the shared sentinel memory region.
 */
static void sentinel_init(void) {
    sentinel_region = mmio_region_from_addr(SENTINEL_BASE);
}

/**
 * Write a 32-bit value to a sentinel address.
 *
 * @param offset Byte offset from SENTINEL_BASE.
 * @param val    Value to write.
 */
static void sentinel_write(ptrdiff_t offset, uint32_t val) {
    mmio_region_write32(sentinel_region, offset, val);
}

/**
 * Read a 32-bit value from a sentinel address.
 *
 * @param offset Byte offset from SENTINEL_BASE.
 * @return Value read.
 */
static uint32_t sentinel_read(ptrdiff_t offset) {
    return mmio_region_read32(sentinel_region, offset);
}

// ── Forward declarations ───────────────────────────────────────────

static void system_init(void);
static void tdu_configure(void);
static void dispatch_workers(void);
static void wait_for_completion(void);
static void signal_success(void);
static void signal_failure(uint32_t code);

/**
 * Main entry point for TITAN firmware.
 *
 * Called from start.S after stack initialization.
 */
int main(void) {
    system_init();
    tdu_configure();
    dispatch_workers();
    wait_for_completion();
    signal_success();

    /* Should never reach here. */
    while (1) {}
    return 0;
}

/**
 * Initialize system state.
 *
 * Writes TITAN sentinel, clears worker sentinels, and resets the
 * TDU energy counter.
 */
static void system_init(void) {
    sentinel_init();

    /* Write TITAN sentinel to prove we're alive. */
    sentinel_write(0x00u, SENTINEL_TITAN_VAL);

    /* Clear worker sentinels (in case of warm restart). */
    sentinel_write(0x04u, 0u);
    sentinel_write(0x08u, 0u);

    /* Clear energy counter for measurement. */
    tdu_clear_energy_counter();
}

/**
 * Configure TDU scheduling parameters.
 *
 * Sets scheduling mode to DYNAMIC and pre-loads CPI estimates for the
 * scheduler. The wake mask is armed in dispatch_workers() after all
 * descriptors are queued: the TDU's auto-wake is targeted by core_hint
 * (bug 20 fix), so this batching is no longer load-bearing, but keeping
 * dispatch independent of the auto-wake path also exercises the explicit
 * WAKE_REQ release and stays robust if the wake semantics ever change.
 */
static void tdu_configure(void) {
    /* Set scheduling mode to DYNAMIC (TITAN migrates tasks based on CPI). */
    tdu_set_sched_mode(TDU_SCHED_DYNAMIC);

    /* Pre-load CPI estimates for the workers (used by DYNAMIC scheduler). */
    for (uint32_t i = 1; i <= NUM_ATLAS; i++) {
        /* ATLAS (fazyrv): CPI ~4 (chunk-serial, moderate speed). */
        tdu_set_cpi_estimate(i, 4u);
    }
    for (uint32_t i = NUM_ATLAS + 1; i <= NUM_WORKERS; i++) {
        /* NANO (serv): CPI ~32 (bit-serial, very slow). */
        tdu_set_cpi_estimate(i, 32u);
    }
}

/**
 * Dispatch tasks to worker cores via the TDU.
 *
 * Signal-processing tasks go to ATLAS (harts 1-2), sensor-polling
 * tasks go to NANO (harts 3-6).
 *
 * Push-all-then-wake: every descriptor must be in the task FIFO before
 * any worker starts, because a woken worker reaches TASK_POP within a
 * few instructions while this dispatch loop takes hundreds of cycles
 * per push — waking incrementally lets fast workers pop an empty FIFO
 * (raw 0 -> sentinel slot 0) and strands the remaining descriptors.
 */
static void dispatch_workers(void) {
    tdu_task_t task;

    /* Queue signal-processing tasks for ATLAS cores. */
    for (uint32_t i = 0; i < NUM_ATLAS; i++) {
        task.task_id   = TASK_ID_SIGNAL_PROC;
        task.core_hint = (uint8_t)(1u + i);
        task.prio      = 0u;
        tdu_task_push(&task);
    }

    /* Queue sensor-polling tasks for NANO cores. */
    for (uint32_t i = 0; i < NUM_NANO; i++) {
        task.task_id   = TASK_ID_SENSOR_POLL;
        task.core_hint = (uint8_t)(NUM_ATLAS + 1u + i);
        task.prio      = 1u;
        tdu_task_push(&task);
    }

    /* All descriptors queued — now arm auto-wake for future pushes and
     * release every worker in one WAKE_REQ pulse. */
    uint32_t worker_mask = ((1u << NUM_WORKERS) - 1u) << 1u;
    tdu_set_wake_mask(worker_mask);
    tdu_wake_harts(worker_mask);
}

/**
 * Poll sentinel addresses until all workers have reported completion.
 *
 * Worker programs write their sentinel value to shared memory after
 * completing their task. This function polls until all sentinels are
 * set or a timeout occurs.
 */
static void wait_for_completion(void) {
    uint32_t timeout = POLL_TIMEOUT;

    /* Wait for ATLAS workers (sentinel slots at offset 0x04 and 0x08). */
    uint32_t atlas_done = 0;
    while (atlas_done < NUM_ATLAS && timeout > 0) {
        uint32_t mask = 0u;
        if (sentinel_read(0x04u) == SENTINEL_ATLAS_VAL) mask |= 1u;
        if (sentinel_read(0x08u) == SENTINEL_ATLAS_VAL) mask |= 2u;
        atlas_done = popcount32(mask);
        timeout--;
    }

    /* Wait for NANO workers (sentinel slots at offset 0x0C..0x18). */
    uint32_t nano_done = 0;
    timeout = POLL_TIMEOUT;
    while (nano_done < NUM_NANO && timeout > 0) {
        uint32_t mask = 0u;
        for (uint32_t i = 0; i < NUM_NANO; i++) {
            ptrdiff_t off = (ptrdiff_t)(0x0Cu + i * 4u);
            if (sentinel_read(off) == SENTINEL_NANO_VAL) mask |= (1u << i);
        }
        nano_done = popcount32(mask);
        timeout--;
    }

    /* Check for timeout. */
    if (atlas_done < NUM_ATLAS || nano_done < NUM_NANO) {
        signal_failure((atlas_done << 16) | nano_done);
    }

    /* Read final energy counter for reporting. */
    (void)tdu_get_energy_counter();
}

/**
 * Signal test success to the SoC testbench.
 */
static void signal_success(void) {
    soc_ctrl_exit(0u);
}

/**
 * Signal test failure with an error code.
 *
 * @code Packed error: (atlas_done << 16) | nano_done.
 */
static void signal_failure(uint32_t code) {
    soc_ctrl_exit(code);
}
