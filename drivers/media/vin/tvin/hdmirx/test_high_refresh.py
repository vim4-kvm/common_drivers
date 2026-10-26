"""Compile the real RX classifiers: 119.88/120 Hz must not fall back to 60 Hz."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).with_name('hdmi_rx_wrapper.c').read_text()


def function(name):
    start = SOURCE.rfind('\n', 0, SOURCE.index(name + '(')) + 1
    brace = SOURCE.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end]


class HighRefreshTest(unittest.TestCase):
    def test_measured_rate_selects_high_refresh_for_all_progressive_1080_aliases(self):
        functions = function('get_fps_index') + '\n' + function('hdmirx_hw_get_fmt')
        enums = '\n'.join('enum ' + name + ' {' + ','.join(sorted(set(re.findall(pattern, functions)))) + '};'
                          for name, pattern in [('fps_e', r'\bE_\d+HZ\b'),
                                                ('hdmi_vic_e', r'\bHDMI_\w+\b'),
                                                ('tvin_sig_fmt_e', r'\bTVIN_SIG_FMT_\w+\b')])
        fixture = r'''
#include <assert.h>
#include <stdlib.h>
typedef unsigned char u8;
static struct { struct { int frame_rate, sw_vic; } pre; } rx[2];
static int force_vic, diff_frame_th=40, en_4k_timing=1;
'''
        assertions = r'''
int main(void) {
 const int aliases[]={HDMI_1080p60, HDMI_1080p100, HDMI_1080p120,
                      HDMI_1080p100_64x27, HDMI_1080p120_64x27};
 const struct { int rate, fmt; } cases[]={
  {2398,TVIN_SIG_FMT_HDMI_1920X1080P_24HZ}, {2400,TVIN_SIG_FMT_HDMI_1920X1080P_24HZ},
  {2500,TVIN_SIG_FMT_HDMI_1920X1080P_25HZ}, {2997,TVIN_SIG_FMT_HDMI_1920X1080P_30HZ},
  {5000,TVIN_SIG_FMT_HDMI_1920X1080P_50HZ}, {5994,TVIN_SIG_FMT_HDMI_1920X1080P_60HZ},
  {6000,TVIN_SIG_FMT_HDMI_1920X1080P_60HZ}, {10000,TVIN_SIG_FMT_HDMI_1920X1080P_100HZ},
  {11988,TVIN_SIG_FMT_HDMI_1920X1080P_120HZ}, {12000,TVIN_SIG_FMT_HDMI_1920X1080P_120HZ}
 };
 for (unsigned i=0;i<sizeof(aliases)/sizeof(aliases[0]);i++) {
  rx[1].pre.sw_vic=aliases[i];
  for (unsigned j=0;j<sizeof(cases)/sizeof(cases[0]);j++) {
   rx[1].pre.frame_rate=cases[j].rate;
   assert(hdmirx_hw_get_fmt(1)==cases[j].fmt);
  }
 }
 rx[1].pre.sw_vic=HDMI_2160p60_16x9;
 rx[1].pre.frame_rate=6000;
 assert(hdmirx_hw_get_fmt(1)==TVIN_SIG_FMT_HDMI_3840_2160_00HZ);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            source, binary = Path(temporary) / 'rx.c', Path(temporary) / 'rx'
            source.write_text(fixture + enums + functions + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                            '-Wno-sign-compare', str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
