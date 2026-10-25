#!/usr/bin/env python3
"""Exercise the real GE2D/MultiEnc rate requests with competing consumers.

The clock mock models rounded rates and per-consumer minimums, not hardware
clock-tree propagation. Run the full kernel build and board tests separately.
"""
import os
from pathlib import Path
import subprocess
import tempfile


def function(source, name):
    start = source.index("static int " + name + "(")
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
typedef unsigned int u32;
#define MHz 1000000UL
#define AM_MESON_CPU_MAJOR_ID_T7 7
#define VDEC_WAVE 1
#define enc_pr(...) ((void)0)
#define dev_err(dev, ...) ((void)(dev))
#define mdelay(...) ((void)0)
#define vdec_poweron(...) ((void)0)
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
struct device { int unused; };
struct clk { unsigned long min; };
struct vpu_clks {
    struct clk *dos_clk, *dos_apb_clk, *a_clk, *b_clk, *c_clk;
};
static u32 set_clock_freq, clock_a, clock_b, clock_c;
static int clock_gate_count, round_error, vote_error;
static struct clk bus[2];
static unsigned long bus_rate;
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
    struct clk core = {0};
    struct vpu_clks clocks = { &core, &bus[1], &core, &core, &core };
    /* GE2D probes before the encoder, as on T7. */
    bus_rate = 399999994;
    assert(!ge2d_set_min_rate(&dev, &bus[0], 667000000));
    for (int i = 0; i < 20; i++) {
        assert(!vpu_clk_enable(&clocks));
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
    assert(!vpu_clk_enable(&clocks));
    assert(bus_rate == 200000000);
    assert(!ge2d_set_min_rate(&dev, &bus[0], 667000000));
    assert(bus_rate == 666666656);
    vpu_clk_disable(&clocks);
    assert(bus[1].min == 0 && bus[0].min == 666666656);
    /* Failed requests must propagate instead of reporting success. */
    round_error = -EIO;
    assert(vpu_clk_enable(&clocks) == -EIO);
    assert(ge2d_set_min_rate(&dev, &bus[0], 667000000) == -EIO);
    round_error = 0;
    vote_error = -ERANGE;
    assert(vpu_clk_enable(&clocks) == -ERANGE);
    assert(ge2d_set_min_rate(&dev, &bus[0], 667000000) == -ERANGE);
    assert(bus[1].min == 0 && bus_rate == 666666656);
    puts("shared clock ordering, reopen, rounding and failures: PASS");
}
"""
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / "clock.c"
    binary = Path(directory) / "clock-test"
    source.write_text(harness + function(ge2d, "ge2d_set_min_rate")
                      + function(encoder, "vpu_clk_enable")
                      + encoder[disable_start:disable_end] + checks)
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                    "-Werror", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
