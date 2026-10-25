import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class AviHdrTest(unittest.TestCase):
    def test_sdr_retirement_does_not_remove_new_hdr_packet(self):
        text = Path(__file__).with_name('hdmi_tx_main.c').read_text()
        start = text.index('static void hdr_work_func(')
        end = text.index('\n#define GET_LOW8BIT', start)
        fixture = r'''
#include <assert.h>
#include <stddef.h>
#define T_BT709 1
#define C_BT709 1
#define CONF_AVI_BT2020 0
#define HDMITX_INFO(...) ((void)0)
#define container_of(pointer, type, member) (&device)
struct work_struct { int unused; };
struct hdmi_drm_infoframe { int unused; };
struct hdmitx_dev {
 struct work_struct work_hdr;
 struct { struct { struct hdmi_drm_infoframe drm; } drm; } infoframes;
 int hdr_transfer_feature, hdr_color_feature, colormetry;
 struct { int hdmi_current_hdr_mode, hdmi_last_hdr_mode; } tx_comm;
};
static struct hdmitx_dev device;
static int hdr_status_pos, disabled, replace_with_hdr;
static void hdmi_drm_infoframe_init(struct hdmi_drm_infoframe *info) { (void)info; }
static void hdmi_drm_infoframe_set(struct hdmi_drm_infoframe *info) { if (!info) disabled++; }
static void hdmi_vend_infoframe_rawset(void *header, void *body) { (void)header; (void)body; }
static void hdmi_avi_infoframe_config(int command, int value) { (void)command; (void)value; }
static void msleep(int duration) { (void)duration; if (replace_with_hdr) device.hdr_transfer_feature=16; }
static void hdmitx_sdr_hdr_uevent(struct hdmitx_dev *dev) { (void)dev; }
'''
        assertions = r'''
int main(void) {
 device.hdr_transfer_feature=T_BT709;
 device.hdr_color_feature=C_BT709;
 hdr_work_func(&device.work_hdr);
 assert(disabled==1);
 replace_with_hdr=1;
 hdr_work_func(&device.work_hdr);
 assert(disabled==1);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / 'drm.c', Path(directory) / 'drm'
            source.write_text(fixture + text[start:end] + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

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
