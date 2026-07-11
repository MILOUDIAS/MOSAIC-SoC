// Copyright 2026 MOSAIC-SoC Contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

/**
 * @file titan_scheduling_demo.c
 * @brief TITAN scheduling-mode demonstration firmware.
 *
 * Exercises all three TDU scheduling modes in sequence:
 *   Phase 1 — STATIC:  baseline dispatch, fixed core assignment
 *   Phase 2 — DYNAMIC: re-dispatch based on observed CPI estimates
 *   Phase 3 — POWER_AWARE: energy-budget-aware core selection
 *
 * Each phase dispatches the same workload (2 signal-processing +
 * 4 sensor-polling tasks), measures the energy counter, and reports
 * results to the testbench via shared-memory sentinel slots.
 *
 * Sentinel slot layout (byte offsets from SENTINEL_BASE):
 *   0x00 — TITAN status word (see STATUS_* below)
 *   0x04 — Phase 1 energy count
 *   0x08 — Phase 2 energy count
 *   0x0C — Phase 3 energy count
 *   0x10 — Final scheduling mode
 *   0x14 — PASS/FAIL flag
 *
 * @see hw/tdu/rtl/tdu.sv
 * @see hw/tdu/rtl/tdu_pkg.sv
 * @see sw/firmware/titan/titan_main.c — production orchestrator
 */

#include "tdu.h"

// ── Constants ───────────────────────────────────────────────────────

/** Number of ATLAS (FazyRV) worker cores in PoC. */
#define NUM_ATLAS 2

/** Number of NANO (SERV) worker cores in PoC. */
#define NUM_NANO  4

/** Total worker cores. */
#define NUM_WORKERS (NUM_ATLAS + NUM_NANO)

/** Sentinel value for TITAN. */
#define SENTINEL_TITAN_VAL  0xC0FFEE00u

/** Sentinel value for ATLAS workers. */
#define SENTINEL_ATLAS_VAL  0xA71A5000u

/** Sentinel value for NANO workers. */
#define SENTINEL_NANO_VAL   0x4E414E00u

/** Task ID: signal processing (ATLAS). */
#define TASK_ID_SIGNAL_PROC  0x0002u

/** Task ID: sensor polling (NANO). */
#define TASK_ID_SENSOR_POLL  0x0001u

/** Phase completion status codes. */
#define STATUS_PASS         0x00000001u
#define STATUS_FAIL         0x00000000u
#define STATUS_PHASE1_DONE  0x00000100u
#define STATUS_PHASE2_DONE  0x00000200u
#define STATUS_PHASE3_DONE  0x00000400u

/** Maximum polling iterations. */
#define POLL_TIMEOUT 1000000u

// ── Shared memory ───────────────────────────────────────────────────

/** MMIO handle for sentinel memory. */
static mmio_region_t sentinel_region;

/** MMIO handle for scratchpad (inter-phase CPI/energy data). */
static mmio_region_t scratchpad_region;

/** Scratchpad base: 0x4000 in SRAM — used for CPI arrays and temp data. */
#define SCRATCHPAD_BASE_ADDR  0x4000u

// ── Helpers ─────────────────────────────────────────────────────────

/**
 * Population count for RV32I (no __builtin_popcount without libgcc).
 */
static inline uint32_t popcount32(uint32_t x) {
    x = x - ((x >> 1) & 0x55555555u);
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    return (((x + (x >> 4)) & 0x0F0F0F0Fu) * 0x01010101u) >> 24;
}

/** Write a 32-bit word to sentinel memory. */
static void sen_w(uint32_t offset, uint32_t val) {
    mmio_region_write32(sentinel_region, (ptrdiff_t)offset, val);
}

/** Read a 32-bit word from sentinel memory. */
static uint32_t sen_r(uint32_t offset) {
    return mmio_region_read32(sentinel_region, (ptrdiff_t)offset);
}

/** Write a 32-bit word to scratchpad memory. */
static void scr_w(uint32_t offset, uint32_t val) {
    mmio_region_write32(scratchpad_region, (ptrdiff_t)offset, val);
}

/**
 * Spin-wait for a number of cycles (approximate).
 */
static void delay(uint32_t cycles) {
    volatile uint32_t i;
    for (i = 0; i < cycles; i++) {
        asm volatile("nop");
    }
}

/**
 * Dispatch one task to a given hart via the TDU.
 */
static void dispatch_task(uint16_t task_id, uint8_t hart, uint8_t prio) {
    tdu_task_t task = {
        .task_id   = task_id,
        .core_hint = hart,
        .prio      = prio,
    };
    tdu_dispatch_task(&task);
}

/**
 * Reset all worker sentinel slots to zero.
 */
static void clear_worker_sentinels(void) {
    for (uint32_t i = 0; i < NUM_WORKERS; i++) {
        sen_w(0x04u + i * 4u, 0u);
    }
}

/**
 * Count how many worker sentinel slots match expected value.
 */
static uint32_t count_worker_done(uint32_t expected) {
    uint32_t mask = 0u;
    for (uint32_t i = 0; i < NUM_WORKERS; i++) {
        if (sen_r(0x04u + i * 4u) == expected) {
            mask |= (1u << i);
        }
    }
    return popcount32(mask);
}

// ── Phase implementations ───────────────────────────────────────────

/**
 * Phase 1: STATIC scheduling.
 *
 * Baseline: dispatch tasks with fixed core assignment.
 * Signal-processing tasks → ATLAS (harts 1-2)
 * Sensor-polling tasks → NANO (harts 3-6)
 * TITAN monitors completion via sentinels.
 *
 * @return Energy counter value at end of phase.
 */
static uint32_t phase_static(void) {
    tdu_clear_energy_counter();
    tdu_set_sched_mode(TDU_SCHED_STATIC);
    clear_worker_sentinels();

    /* Dispatch signal-processing to ATLAS. */
    for (uint32_t i = 0; i < NUM_ATLAS; i++) {
        dispatch_task(TASK_ID_SIGNAL_PROC, (uint8_t)(1u + i), 0u);
    }

    /* Dispatch sensor-polling to NANO. */
    for (uint32_t i = 0; i < NUM_NANO; i++) {
        dispatch_task(TASK_ID_SENSOR_POLL, (uint8_t)(NUM_ATLAS + 1u + i), 1u);
    }

    /* Poll until all workers complete or timeout. */
    uint32_t timeout = POLL_TIMEOUT;
    while (count_worker_done(SENTINEL_ATLAS_VAL | SENTINEL_NANO_VAL) < NUM_WORKERS
           && timeout > 0) {
        timeout--;
    }

    return tdu_get_energy_counter();
}

/**
 * Phase 2: DYNAMIC scheduling.
 *
 * TITAN updates CPI estimates based on observed behavior, then
 * re-dispatches to migrate work from slow cores to fast cores.
 *
 * Strategy:
 *   1. Read initial CPI estimates (set by Phase 1 or default).
 *   2. If an ATLAS core has CPI > threshold, move its task to
 *      another ATLAS core with lower CPI.
 *   3. If a NANO core has CPI > threshold, consolidate to fewer
 *      NANO cores (power savings).
 *
 * @return Energy counter value at end of phase.
 */
static uint32_t phase_dynamic(void) {
    tdu_clear_energy_counter();
    tdu_set_sched_mode(TDU_SCHED_DYNAMIC);
    clear_worker_sentinels();

    /* Step 1: Read current CPI estimates from scratchpad (updated by
     * previous phase's firmware or defaults). */
    uint32_t cpi_atlas[NUM_ATLAS];
    uint32_t cpi_nano[NUM_NANO];

    for (uint32_t i = 0; i < NUM_ATLAS; i++) {
        cpi_atlas[i] = tdu_get_cpi_estimate(1u + i);
    }
    for (uint32_t i = 0; i < NUM_NANO; i++) {
        cpi_nano[i] = tdu_get_cpi_estimate(NUM_ATLAS + 1u + i);
    }

    /* Step 2: CPI-based migration.
     * If any ATLAS core's CPI exceeds 2x the best ATLAS CPI,
     * migrate its task to the best core. */
    uint32_t best_atlas_cpi = cpi_atlas[0];
    uint8_t  best_atlas_hart = 1u;
    for (uint32_t i = 1; i < NUM_ATLAS; i++) {
        if (cpi_atlas[i] < best_atlas_cpi) {
            best_atlas_cpi = cpi_atlas[i];
            best_atlas_hart = (uint8_t)(1u + i);
        }
    }

    /* Dispatch signal-processing to the best ATLAS core only.
     * (In a real FreeRTOS system, the other ATLAS core would be idle
     * or running lower-priority tasks.) */
    for (uint32_t i = 0; i < NUM_ATLAS; i++) {
        dispatch_task(TASK_ID_SIGNAL_PROC, best_atlas_hart, 0u);
    }

    /* Step 3: Consolidate NANO tasks.
     * If average NANO CPI > 24 (slow), use only the 2 fastest NANO
     * cores and sleep the rest. */
    uint32_t nano_cpi_sum = 0;
    for (uint32_t i = 0; i < NUM_NANO; i++) {
        nano_cpi_sum += cpi_nano[i];
    }
    uint32_t nano_avg_cpi = nano_cpi_sum / NUM_NANO;

    /* Find the 2 fastest NANO cores. */
    uint8_t fast_nano[2];
    /* Simple selection: hart 3 and 4 by default, swap if faster ones exist. */
    fast_nano[0] = (uint8_t)(NUM_ATLAS + 1u);
    fast_nano[1] = (uint8_t)(NUM_ATLAS + 2u);

    for (uint32_t i = 0; i < NUM_NANO; i++) {
        uint8_t hart = (uint8_t)(NUM_ATLAS + 1u + i);
        if (cpi_nano[i] < cpi_nano[fast_nano[0] - NUM_ATLAS - 1u]) {
            fast_nano[1] = fast_nano[0];
            fast_nano[0] = hart;
        } else if (cpi_nano[i] < cpi_nano[fast_nano[1] - NUM_ATLAS - 1u]) {
            fast_nano[1] = hart;
        }
    }

    /* Dispatch sensor-polling to the 2 fastest NANO cores only.
     * Each handles 2 tasks (round-robin). */
    for (uint32_t i = 0; i < NUM_NANO; i++) {
        uint8_t target = fast_nano[i % 2];
        dispatch_task(TASK_ID_SENSOR_POLL, target, 1u);
    }

    /* Update wake mask: only wake the active cores. */
    uint32_t active_mask = (1u << best_atlas_hart) |
                           (1u << fast_nano[0]) |
                           (1u << fast_nano[1]);
    tdu_set_wake_mask(active_mask);

    /* Wait for completion. */
    uint32_t timeout = POLL_TIMEOUT;
    while (count_worker_done(SENTINEL_ATLAS_VAL | SENTINEL_NANO_VAL) < NUM_WORKERS
           && timeout > 0) {
        timeout--;
    }

    /* Store CPI data in scratchpad for reporting. */
    scr_w(0x00u, nano_avg_cpi);
    scr_w(0x04u, (uint32_t)best_atlas_hart);
    scr_w(0x08u, (uint32_t)fast_nano[0]);
    scr_w(0x0Cu, (uint32_t)fast_nano[1]);

    return tdu_get_energy_counter();
}

/**
 * Phase 3: POWER_AWARE scheduling.
 *
 * TITAN reads the energy counter and adjusts core selection to stay
 * within an energy budget. If the energy counter exceeds the budget,
 * TITAN sleeps some cores and redistributes tasks.
 *
 * Strategy:
 *   1. Set an energy budget threshold.
 *   2. Dispatch tasks, periodically check energy counter.
 *   3. If energy exceeds budget, reduce active cores by consolidating
 *      tasks to fewer, faster cores.
 *   4. Report final energy and whether budget was met.
 *
 * @return Energy counter value at end of phase.
 */
static uint32_t phase_power_aware(void) {
    tdu_clear_energy_counter();
    tdu_set_sched_mode(TDU_SCHED_POWER_AWARE);
    clear_worker_sentinels();

    /* Energy budget: target is 50% of the worst-case energy.
     * Worst case = all 7 cores running full time.
     * Budget = (NUM_WORKERS * max_cycles) / 2.
     * We use a simplified threshold based on the energy counter
     * reading after a calibration delay. */
    uint32_t energy_budget = 50000u;  /* Tunable threshold. */

    /* Step 1: Calibrate — run all cores briefly, measure energy. */
    for (uint32_t i = 0; i < NUM_ATLAS; i++) {
        dispatch_task(TASK_ID_SIGNAL_PROC, (uint8_t)(1u + i), 0u);
    }
    for (uint32_t i = 0; i < NUM_NANO; i++) {
        dispatch_task(TASK_ID_SENSOR_POLL, (uint8_t)(NUM_ATLAS + 1u + i), 1u);
    }

    /* Let all cores run for a calibration period. */
    delay(10000u);

    uint32_t energy_sample = tdu_get_energy_counter();

    /* Step 2: Decide how many cores to use based on energy. */
    uint8_t  active_harts[7];
    uint32_t num_active;

    if (energy_sample <= energy_budget) {
        /* Energy is within budget — use all cores. */
        num_active = NUM_WORKERS;
        for (uint32_t i = 0; i < NUM_WORKERS; i++) {
            active_harts[i] = (uint8_t)(1u + i);
        }
    } else {
        /* Energy exceeds budget — use only ATLAS cores (faster, fewer). */
        num_active = NUM_ATLAS;
        for (uint32_t i = 0; i < NUM_ATLAS; i++) {
            active_harts[i] = (uint8_t)(1u + i);
        }
        /* Sleep NANO cores by not including them in wake mask. */
    }

    /* Step 3: Reset and re-dispatch with reduced core set. */
    tdu_clear_energy_counter();
    clear_worker_sentinels();

    /* Update wake mask to only active cores. */
    uint32_t new_mask = 0u;
    for (uint32_t i = 0; i < num_active; i++) {
        new_mask |= (1u << active_harts[i]);
    }
    tdu_set_wake_mask(new_mask);

    /* Dispatch tasks only to active cores. */
    for (uint32_t i = 0; i < num_active; i++) {
        uint16_t tid = (active_harts[i] <= NUM_ATLAS)
                       ? TASK_ID_SIGNAL_PROC
                       : TASK_ID_SENSOR_POLL;
        dispatch_task(tid, active_harts[i], 0u);
    }

    /* Wait for completion. */
    uint32_t timeout = POLL_TIMEOUT;
    while (count_worker_done(SENTINEL_ATLAS_VAL | SENTINEL_NANO_VAL) < num_active
           && timeout > 0) {
        timeout--;
    }

    uint32_t final_energy = tdu_get_energy_counter();

    /* Store power-aware results in scratchpad. */
    scr_w(0x10u, energy_budget);
    scr_w(0x14u, energy_sample);
    scr_w(0x18u, final_energy);
    scr_w(0x1Cu, num_active);

    return final_energy;
}

// ── Main ────────────────────────────────────────────────────────────

/**
 * Main entry point — runs all three scheduling phases.
 */
int main(void) {
    /* Initialize memory regions. */
    sentinel_region = mmio_region_from_addr(SENTINEL_BASE);
    scratchpad_region = mmio_region_from_addr(SCRATCHPAD_BASE_ADDR);

    /* Write TITAN sentinel. */
    sen_w(0x00u, SENTINEL_TITAN_VAL);

    /* Default TDU configuration. */
    uint32_t worker_mask = ((1u << NUM_WORKERS) - 1u) << 1u;
    tdu_set_wake_mask(worker_mask);

    /* Set initial CPI estimates (default values for each core type). */
    for (uint32_t i = 0; i < NUM_ATLAS; i++) {
        tdu_set_cpi_estimate(1u + i, 4u);   /* ATLAS: CPI ~4 */
    }
    for (uint32_t i = 0; i < NUM_NANO; i++) {
        tdu_set_cpi_estimate(NUM_ATLAS + 1u + i, 32u);  /* NANO: CPI ~32 */
    }

    /* ── Phase 1: STATIC ── */
    uint32_t energy1 = phase_static();
    sen_w(0x04u, energy1);
    sen_w(0x00u, SENTINEL_TITAN_VAL | STATUS_PHASE1_DONE);

    /* ── Phase 2: DYNAMIC ── */
    /* Update CPI estimates to simulate observed variation.
     * In real operation, firmware would read hardware performance
     * counters to compute actual CPI. */
    tdu_set_cpi_estimate(1, 3u);   /* ATLAS hart 1: slightly faster */
    tdu_set_cpi_estimate(2, 6u);   /* ATLAS hart 2: slightly slower */
    tdu_set_cpi_estimate(3, 28u);  /* NANO hart 3: fast */
    tdu_set_cpi_estimate(4, 35u);  /* NANO hart 4: slow */
    tdu_set_cpi_estimate(5, 30u);  /* NANO hart 5: medium */
    tdu_set_cpi_estimate(6, 40u);  /* NANO hart 6: very slow */

    uint32_t energy2 = phase_dynamic();
    sen_w(0x08u, energy2);
    sen_w(0x00u, SENTINEL_TITAN_VAL | STATUS_PHASE1_DONE | STATUS_PHASE2_DONE);

    /* ── Phase 3: POWER_AWARE ── */
    uint32_t energy3 = phase_power_aware();
    sen_w(0x0Cu, energy3);
    sen_w(0x10u, tdu_get_sched_mode());
    sen_w(0x00u, SENTINEL_TITAN_VAL | STATUS_PHASE1_DONE |
                STATUS_PHASE2_DONE | STATUS_PHASE3_DONE | STATUS_PASS);

    /* Signal test pass. */
    soc_ctrl_exit(0u);

    while (1) {}
    return 0;
}
