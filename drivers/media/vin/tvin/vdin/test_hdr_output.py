import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).with_name('vdin_ctl.c').read_text()


def function(name):
    start = SOURCE.rfind('\n', 0, SOURCE.index(name + '(')) + 1
    brace = SOURCE.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end]


class HdrOutputTest(unittest.TestCase):
    def test_native_display_and_secondary_capture_use_independent_hdr_cores(self):
        fixtures = r'''
#include <assert.h>
#include <stdbool.h>
enum vd_format_e { SIGNAL_SDR, SIGNAL_HDR10, SIGNAL_HDR10PLUS, SIGNAL_HLG, SIGNAL_DOVI };
enum { VDIN0_HDR, VDIN1_HDR, VPP_TOP0, HDR_SDR=2, HDR_BYPASS=4, HLG_BYPASS=8,
       HLG_SDR=16, TVIN_PORT_VIU1_VIDEO=100, TVIN_PORT_VIU1_WB0_VD1,
       TVIN_PORT_VIU1_WB0_VD2, TVIN_PORT_VIU1_WB0_POST_BLEND, TVIN_PORT_VIU1_WB1_POST_BLEND,
       TVIN_PORT_VIU1_WB1_VD1, TVIN_PORT_VIU1_WB1_VD2, TVIN_PORT_VIU1_WB0_OSD1,
       TVIN_PORT_VIU1_WB0_OSD2, TVIN_PORT_VIU1_WB1_OSD1, TVIN_PORT_VIU1_WB1_OSD2,
       TVIN_PORT_VIU1_WB0_VPP, TVIN_PORT_VIU1_WB1_VPP, TVIN_PORT_VIU2_ENCL,
       TVIN_PORT_VIU2_ENCI, TVIN_PORT_VIU2_ENCP };
#define IS_HDMI_SRC(port) ((port)==1)
#define WRITE_ONCE(field,value) ((field)=(value))
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
struct vdin_dev_s {
 unsigned index, vd1_fmt, tx_fmt, frame_drop_num;
 bool shared_hdmi_frontend, hdr_sdr_output;
 struct { bool vdin1_set_hdr_bypass; } debug;
 struct { bool vdin0_set_hdr, vdin1_set_hdr; } *dtdata;
 struct { unsigned port; } parm;
};
static bool vdin0_native_hdr;
static enum vd_format_e input_format=SIGNAL_HDR10;
static unsigned selected_core, selected_process;
static enum vd_format_e vdin_hdmi_signal_format(struct vdin_dev_s *devp)
{ (void)devp; return input_format; }
static void hdr_set(unsigned core, unsigned process, unsigned top)
{ selected_core=core; selected_process=process; (void)top; }
'''
        assertions = r'''
int main(void) {
 struct vdin_dev_s primary={ .parm.port=1 };
 primary.dtdata=&(typeof(*primary.dtdata)){true,true};
 struct vdin_dev_s secondary={ .index=1, .dtdata=primary.dtdata, .parm.port=1,
                               .shared_hdmi_frontend=true, .tx_fmt=SIGNAL_SDR };
 vdin_set_hdr(&primary);
 assert(selected_core==VDIN0_HDR && selected_process==HDR_SDR && primary.hdr_sdr_output);
 vdin0_native_hdr=true;
 vdin_set_hdr(&primary);
 assert(selected_core==VDIN0_HDR && selected_process==(HDR_BYPASS|HLG_BYPASS));
 assert(!primary.hdr_sdr_output);
 vdin_set_hdr(&secondary);
 assert(selected_core==VDIN1_HDR && selected_process==HDR_SDR && secondary.hdr_sdr_output);
 input_format=SIGNAL_HLG;
 vdin_set_hdr(&secondary);
 assert(selected_process==HLG_SDR && secondary.hdr_sdr_output);
 input_format=SIGNAL_SDR;
 vdin_set_hdr(&secondary);
 assert(selected_process==(HDR_BYPASS|HLG_BYPASS) && !secondary.hdr_sdr_output);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'hdr-cores.c'
            binary = Path(temporary) / 'hdr-cores'
            source.write_text(fixtures + function('vdin_set_hdr') + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_hdr_nv21_memory_layout_and_tonemapped_metadata(self):
        fixtures = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;
#define CONFIG_AMLOGIC_ZAPPER_CUT
enum vdin_color_deeps_e { VDIN_COLOR_DEEPS_8BIT=8, VDIN_COLOR_DEEPS_10BIT=10,
                          VDIN_COLOR_DEEPS_12BIT=12 };
static const bool vdin_dbg_en=false;
enum { COLOR_DEEPS_AUTO=0, COLOR_DEEPS_8BIT=8, COLOR_DEEPS_10BIT=10,
       COLOR_DEEPS_12BIT=12, VDIN_WR_COLOR_DEPTH_10BIT_FULL_PACK_MODE=2,
       VDIN_422_FULL_PK_EN=1, VDIN_422_FULL_PK_DIS=0,
       TVIN_SIG_FMT_HDMI_3840_2160_00HZ=1, TVIN_SIG_FMT_HDMI_4096_2160_00HZ=2,
       VDIN_WR_COLOR_DEPTH_10BIT=1, MESON_CPU_MAJOR_ID_T3=3, VDIN_WORK_MD_V4L=1,
       VDIN_WR_CTRL2=1, VDIN_WR_10BIT_MODE_BIT=0, VDIN_WR_10BIT_MODE_WID=1, MIF_8BIT=0 };
struct vdin_dev_s {
 unsigned addr_offset, output_color_depth, color_depth_support, full_pack,
          color_depth_config, format_convert, index, set_canvas_manual,
          work_mode, source_bitdepth;
 struct { unsigned fps, colordepth, vdin_hdr_flag; } prop;
 struct { unsigned port; struct { unsigned fmt; } info; } parm;
};
#define IS_HDMI_SRC(port) ((port)==1)
#define wr_bits(device_offset, ...) ((void)(device_offset))
#define pr_info(...) ((void)0)
static bool vdin_is_convert_to_444(unsigned format) { return format==4; }
static bool vdin_is_convert_to_422(unsigned format) { return format==2; }
static bool vdin_is_convert_to_nv21(unsigned format) { return format==12 || format==13; }
static bool vdin_is_4k(struct vdin_dev_s *devp) { (void)devp; return true; }
static bool cpu_after_eq(unsigned cpu) { (void)cpu; return true; }
static bool vdin_is_dolby_tunnel_444_input(struct vdin_dev_s *devp) { (void)devp; return false; }
static bool vdin_is_support_10bit_for_dw(struct vdin_dev_s *devp) { (void)devp; return true; }
struct vframe_s {
 u32 signal_type, ext_signal_type;
 struct { unsigned master_display_colour[16], hdr10p_data[8]; } prop;
 struct { unsigned size; } drm_if, emp;
};
'''
        assertions = r'''
int main(void) {
 struct vdin_dev_s device = { .prop={ .fps=60, .colordepth=8, .vdin_hdr_flag=1 },
     .parm={ .port=1 }, .color_depth_support=1, .format_convert=12 };
 struct vframe_s frame;
 vdin_set_bitdepth(&device);
 assert(device.source_bitdepth==8);
 device.format_convert=13;
 vdin_set_bitdepth(&device);
 assert(device.source_bitdepth==8);
 device.format_convert=2;
 vdin_set_bitdepth(&device);
 assert(device.source_bitdepth==10);
 memset(&frame, 0xff, sizeof(frame));
 vdin_set_sdr_metadata(&frame);
 assert((frame.signal_type & 0xffffff)==0x010101);
 assert(!(frame.signal_type & ((1U<<29)|(1U<<25))));
 assert((frame.ext_signal_type & 0xff00)==0x0200);
 assert(frame.drm_if.size==0 && frame.emp.size==0);
 for (unsigned index=0;index<16;index++) assert(frame.prop.master_display_colour[index]==0);
 for (unsigned index=0;index<8;index++) assert(frame.prop.hdr10p_data[index]==0);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'hdr-output.c'
            binary = Path(temporary) / 'hdr-output'
            source.write_text(fixtures + function('vdin_set_bitdepth') + '\n' +
                              function('vdin_set_sdr_metadata') + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
