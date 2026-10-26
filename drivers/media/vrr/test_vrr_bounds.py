"""Compile real VRR control functions with bounded register/device fixtures."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


def function(path, name):
    source = path.read_text()
    start = source.rfind('\n', 0, source.index(name + '(')) + 1
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def run_c(body):
    with tempfile.TemporaryDirectory() as directory:
        source, binary = Path(directory) / 'test.c', Path(directory) / 'test'
        source.write_text('#include <assert.h>\n#include <stdio.h>\n#include <string.h>\n' + body)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                        str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


class VrrBoundsTest(unittest.TestCase):
    def test_sink_ranges_and_current_encoder_are_used_without_division_by_zero(self):
        source = Path(__file__).parents[1] / 'vout/hdmitx21/hdmi_tx_vrr.c'
        run_c(r'''
typedef unsigned long long u64;
#define VMODE_HDMI 1
#define VRR_OUTPUT_ENCP 0
#define VRR_NAME_LEN_MAX 30
#define HDMITX_INFO(...) do { if (0) printf(__VA_ARGS__); } while (0)
struct rx_cap { unsigned vrr_min, vrr_max; };
struct vinfo_s { unsigned mode, vtotal, sync_duration_num, sync_duration_den; };
struct vrr_device_s { unsigned output_src,vfreq_max,vfreq_min,vline_max,vline_min,vline,enable; char name[30]; };
struct hdmitx_dev { struct { struct rx_cap rxcap; struct vinfo_s hdmitx_vinfo; unsigned enc_idx; } tx_comm; struct vrr_device_s hdmitx_vrr_dev; };
static unsigned registered_index;
static u64 div_u64(u64 n,unsigned d) { assert(d); return n/d; }
static int aml_vrr_register_device(struct vrr_device_s *d,unsigned i) { registered_index=i; return d->enable; }
''' + function(source, 'hdmitx_register_vrr') + r'''
int main(void) {
 struct hdmitx_dev d={.tx_comm={.hdmitx_vinfo={VMODE_HDMI,1125,120,1},.enc_idx=2}};
 hdmitx_register_vrr(&d);
 assert(registered_index==2 && !d.hdmitx_vrr_dev.enable);
 assert(d.hdmitx_vrr_dev.vline_max==0);
 d.tx_comm.rxcap=(struct rx_cap){48,120};
 hdmitx_register_vrr(&d);
 assert(d.hdmitx_vrr_dev.enable && d.hdmitx_vrr_dev.vfreq_min==48);
 assert(d.hdmitx_vrr_dev.vfreq_max==120 && d.hdmitx_vrr_dev.vline_max==2812);
 d.tx_comm.hdmitx_vinfo.sync_duration_num=60;
 hdmitx_register_vrr(&d);
 assert(d.hdmitx_vrr_dev.vline_max==1406 && d.hdmitx_vrr_dev.vline_min==1125);
 d.tx_comm.hdmitx_vinfo.sync_duration_num=60000;
 d.tx_comm.hdmitx_vinfo.sync_duration_den=1001;
 hdmitx_register_vrr(&d);
 assert(d.hdmitx_vrr_dev.vline_max==1404);
 d.tx_comm.rxcap=(struct rx_cap){120,48};
 hdmitx_register_vrr(&d);
 assert(!d.hdmitx_vrr_dev.enable && !d.hdmitx_vrr_dev.vline_max);
 d.tx_comm.rxcap=(struct rx_cap){48,120};
 d.tx_comm.hdmitx_vinfo.sync_duration_den=0;
 hdmitx_register_vrr(&d);
 assert(!d.hdmitx_vrr_dev.enable);
 d.tx_comm.hdmitx_vinfo=(struct vinfo_s){VMODE_HDMI,1125,30,1};
 hdmitx_register_vrr(&d);
 assert(!d.hdmitx_vrr_dev.enable);
 d.tx_comm.hdmitx_vinfo=(struct vinfo_s){VMODE_HDMI,1125,120,1};
 d.tx_comm.rxcap=(struct rx_cap){1,120};
 hdmitx_register_vrr(&d);
 assert(!d.hdmitx_vrr_dev.enable);
 return 0;
}
''')

    def test_delay_changes_at_constant_crop_use_offset_once_and_correct_write_phase(self):
        source = Path(__file__).with_name('vrr_drv.c')
        run_c(r'''
#define VRR_DBG_PR_NORMAL 1
#define VRR_STATE_TRACE 2
#define VRR_OUTPUT_ENCP 0
#define VRR_OUTPUT_ENCL 1
#define VRR_CHIP_T3X 3
#define VENP_VRR_CTRL 0x100
#define VENC_VRR_CTRL 0x200
#define VENC_VRR_CTRL_T3X 0x300
#define VRRPR(...) ((void)0)
#define VRRERR(...) ((void)0)
struct aml_vrr_drv_s { unsigned index,state,line_dly; struct {unsigned output_src;} *vrr_dev; struct {unsigned offset[3],chip_type;} *data; };
static unsigned vrr_debug_print,crop_line,pre_line,vrr_line_dly,vrr_vpp_index;
static unsigned value,read_reg,written_reg,immediate,deferred;
static void vrr_drv_trace(struct aml_vrr_drv_s *d,char *s) { (void)d;(void)s; }
static unsigned vrr_reg_getb(unsigned r,unsigned s,unsigned n) {read_reg=r;return value;}
static void vrr_reg_setb(unsigned r,unsigned v,unsigned s,unsigned n) {written_reg=r;value=v;immediate++;}
#define VSYNC_WRITE_VPP_REG_BITS_VPP_SEL(r,v,s,n,i) do {(void)(i);written_reg=r;value=v;deferred++;} while(0)
''' + function(source, 'vrr_line_delay_update') + r'''
int main(void) {
 struct aml_vrr_drv_s d={.index=1,.line_dly=100};
 typeof(*d.vrr_dev) output={.output_src=VRR_OUTPUT_ENCP};
 typeof(*d.data) data={.offset={0,0x600,0},.chip_type=0};
 d.vrr_dev=&output;d.data=&data;
 value=90;crop_line=pre_line=0;
 vrr_line_delay_update(&d);
 assert(read_reg==0x700 && written_reg==0x700 && value==100 && immediate==1);
 d.line_dly=80;
 vrr_line_delay_update(&d);
 assert(value==80 && deferred==1 && written_reg==0x700);
 vrr_line_delay_update(&d);
 assert(immediate==1 && deferred==1);
 crop_line=20;
 vrr_line_delay_update(&d);
 assert(value==100 && immediate==2 && pre_line==20);
 crop_line=0;
 vrr_line_delay_update(&d);
 assert(value==80 && deferred==2 && pre_line==0);
 return 0;
}
''')


if __name__ == '__main__':
    unittest.main()
