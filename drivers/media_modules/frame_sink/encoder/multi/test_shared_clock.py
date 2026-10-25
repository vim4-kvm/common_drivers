#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the real GE2D/MultiEnc rate requests with competing consumers.

The clock mock models rounded rates and per-consumer minimums, not hardware
clock-tree propagation. Run the full kernel build and board tests separately.
"""
import os
from pathlib import Path
import subprocess
import tempfile


def function(source, name, result="int"):
    start = source.index("static " + result + " " + name + "(")
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


root = Path(__file__).resolve().parents[4]
encoder = Path(__file__).with_name("vpu_multi.c").read_text()
ge2d = (root / "media/common/ge2d/ge2d_main.c").read_text()
disable_start = encoder.index("static void vpu_clk_disable(")
disable_end = encoder.index("/* end customer definition */", disable_start)

harness = r"""
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
typedef unsigned int u32;
typedef int s32;
typedef unsigned long ulong;
#define CONFIG_CMA 1
#define PAGE_SHIFT 12
#define VPU_DEV_NAME "encoder"
#define MHz 1000000UL
#define AM_MESON_CPU_MAJOR_ID_T7 7
#define VDEC_WAVE 1
#define enc_pr(...) ((void)0)
#define dev_err(dev, ...) ((void)(dev))
#define mdelay(...) ((void)0)
#define vdec_poweron(...) (power_starts++)
#define vdec_poweroff(...) ((void)0)
#define vdec_on(...) 1
#define pm_runtime_get_sync(...) ((void)0)
#define pm_runtime_put_sync(...) ((void)0)
#define pm_runtime_active(...) 1
#define hw_reset(...) ((void)0)
#define clk_prepare_enable(...) ((void)0)
#define clk_disable(...) ((void)0)
#define clk_unprepare(...) ((void)0)
#define clk_disable_unprepare(...) ((void)0)
#define spin_lock(...) ((void)0)
#define spin_unlock(...) ((void)0)
#define vpu_irq_handler 0
struct device { int unused; };
struct inode { int unused; };
struct file { void *private_data; };
struct clk { unsigned long min; };
struct vpu_clks {
    struct clk *dos_clk, *dos_apb_clk, *a_clk, *b_clk, *c_clk;
};
static u32 set_clock_freq, clock_a, clock_b, clock_c;
static int clock_gate_count, round_error, vote_error;
static int power_starts, allocation_failure, allocations, irq_error;
static bool use_reserve, s_vpu_irq_requested;
static int s_vpu_irq = -1;
static u32 cma_cfg_size = 4096;
static struct { int open_count; } s_vpu_drv_context;
struct vpudrv_buffer_t { ulong phys_addr, base; u32 size; };
struct video_mm_t { int unused; };
static struct vpudrv_buffer_t s_video_memory;
static struct video_mm_t s_vmem;
static struct vpu_clks s_vpu_clks;
static struct clk bus[2];
static unsigned long bus_rate;
static ulong codec_mm_alloc_for_dma(const char *name, u32 pages, int a, int b)
{
    (void)name; (void)pages; (void)a; (void)b;
    allocations++;
    return allocation_failure ? 0 : 4096;
}
static void codec_mm_free_for_dma(const char *name, u32 address)
{ (void)name; (void)address; }
static int vmem_init(struct video_mm_t *mm, ulong address, u32 size)
{ (void)mm; (void)address; (void)size; return 0; }
static void vmem_exit(struct video_mm_t *mm) { (void)mm; }
static int request_irq(int irq, int handler, int flags, const char *name, void *dev)
{ (void)irq; (void)handler; (void)flags; (void)name; (void)dev; return irq_error; }
static int get_cpu_major_id(void) { return AM_MESON_CPU_MAJOR_ID_T7; }
static long clk_round_rate(struct clk *clk, unsigned long rate)
{
    (void)clk;
    if (round_error) return round_error;
    if (rate >= 666000000) return 666666656;
    if (rate >= 399000000) return 399999994;
    return rate;
}
static int clk_set_rate(struct clk *clk, unsigned long rate)
{
    if (clk != &bus[0] && clk != &bus[1]) return 0;
    rate = clk_round_rate(clk, rate);
    if (rate < bus[0].min || rate < bus[1].min) return -EINVAL;
    bus_rate = rate;
    return 0;
}
static int clk_set_min_rate(struct clk *clk, unsigned long rate)
{
    if (vote_error) return vote_error;
    clk->min = rate;
    if (bus_rate < rate) bus_rate = rate;
    return 0;
}
"""
checks = r"""
int main(void)
{
    struct device dev;
    struct inode inode;
    struct file file;
    struct clk core = {0};
    struct vpu_clks clocks = { &core, &bus[1], &core, &core, &core };
    /* GE2D probes before the encoder, as on T7. */
    bus_rate = 399999994;
    assert(!ge2d_set_min_rate(&dev, &bus[0], 667000000));
    for (int i = 0; i < 20; i++) {
        assert(!vpu_clk_request_apb(&clocks));
        vpu_clk_enable(&clocks);
        assert(bus_rate == 666666656);
        /* A legacy JPEG exact-rate request cannot lower GE2D's floor. */
        assert(clk_set_rate(&bus[1], 400000000) == -EINVAL);
        vpu_clk_disable(&clocks);
        assert(bus[1].min == 0 && bus_rate == 666666656);
    }
    /* Reversed probe/open order and an explicitly lower encoder request. */
    bus[0].min = 0;
    bus_rate = 100000000;
    set_clock_freq = 200;
    assert(!vpu_clk_request_apb(&clocks));
    vpu_clk_enable(&clocks);
    assert(bus_rate == 200000000);
    assert(!ge2d_set_min_rate(&dev, &bus[0], 667000000));
    assert(bus_rate == 666666656);
    vpu_clk_disable(&clocks);
    assert(bus[1].min == 0 && bus[0].min == 666666656);
    /* Failed requests must propagate instead of reporting success. */
    s_vpu_clks = clocks;
    power_starts = 0;
    round_error = -EIO;
    assert(vpu_open(&inode, &file) == -EIO);
    assert(!allocations && !power_starts && !s_vpu_drv_context.open_count);
    assert(ge2d_set_min_rate(&dev, &bus[0], 667000000) == -EIO);
    round_error = 0;
    vote_error = -ERANGE;
    assert(vpu_open(&inode, &file) == -ERANGE);
    assert(!allocations && !power_starts && !s_vpu_drv_context.open_count);
    assert(ge2d_set_min_rate(&dev, &bus[0], 667000000) == -ERANGE);
    assert(bus[1].min == 0 && bus_rate == 666666656);
    /* Later allocation/IRQ failures must release the accepted bus vote. */
    vote_error = 0;
    allocation_failure = 1;
    assert(vpu_open(&inode, &file) == -ENOMEM);
    assert(allocations == 1 && !power_starts && !s_vpu_drv_context.open_count);
    assert(bus[1].min == 0);
    use_reserve = true;
    s_video_memory.phys_addr = 4096;
    s_vpu_irq = 1;
    irq_error = -EBUSY;
    assert(vpu_open(&inode, &file) == -EFAULT);
    assert(!power_starts && !s_vpu_drv_context.open_count && bus[1].min == 0);
    puts("shared clock ordering, reopen, rounding and failures: PASS");
}
"""
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / "clock.c"
    binary = Path(directory) / "clock-test"
    source.write_text(harness + function(ge2d, "ge2d_set_min_rate")
                      + function(encoder, "vpu_clk_request_apb")
                      + function(encoder, "vpu_clk_enable", "void")
                      + encoder[disable_start:disable_end]
                      + function(encoder, "vpu_open", "s32") + checks)
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                    "-Wno-unused-parameter",
                    "-Werror", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
