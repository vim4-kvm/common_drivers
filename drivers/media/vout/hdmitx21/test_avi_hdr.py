import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class AviHdrTest(unittest.TestCase):
    def test_modeset_retains_hdr_colorimetry_without_marking_sdr_as_hdr(self):
        text = Path(__file__).with_name('hdmi_tx_video.c').read_text()
        start = text.index('static bool hdmitx_use_bt2020(')
        end = text.index('\nstatic void construct_avi_packet', start)
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
typedef unsigned u32;
enum { C_BT709=1, C_BT2020=9, T_BT709=1, T_BT2020_10=14,
       T_SMPTE_ST_2084=16, T_HLG=18 };
struct hdmitx_dev {
 struct { struct { struct { u32 hdr_support; } hdr_info2; } rxcap; } tx_comm;
 unsigned colormetry, hdr_color_feature, hdr_transfer_feature;
};
'''
        assertions = r'''
int main(void) {
 struct hdmitx_dev device={ .hdr_color_feature=C_BT2020,
                           .hdr_transfer_feature=T_SMPTE_ST_2084 };
 device.tx_comm.rxcap.hdr_info2.hdr_support=4;
 assert(hdmitx_use_bt2020(&device));
 device.hdr_transfer_feature=T_HLG;
 assert(!hdmitx_use_bt2020(&device));
 device.tx_comm.rxcap.hdr_info2.hdr_support=8;
 assert(hdmitx_use_bt2020(&device));
 device.hdr_transfer_feature=T_BT2020_10;
 assert(hdmitx_use_bt2020(&device));
 device.hdr_transfer_feature=T_BT709;
 assert(!hdmitx_use_bt2020(&device));
 device.hdr_transfer_feature=T_SMPTE_ST_2084;
 device.tx_comm.rxcap.hdr_info2.hdr_support=0;
 assert(!hdmitx_use_bt2020(&device));
 device.tx_comm.rxcap.hdr_info2.hdr_support=4;
 device.hdr_color_feature=C_BT709;
 assert(!hdmitx_use_bt2020(&device));
 device.colormetry=1;
 assert(hdmitx_use_bt2020(&device));
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / 'avi.c', Path(directory) / 'avi'
            source.write_text(fixture + text[start:end] + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
