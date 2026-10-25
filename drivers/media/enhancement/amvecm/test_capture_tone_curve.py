import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class CaptureCurveTest(unittest.TestCase):
    def test_precise_gamut_is_scoped_to_stock_t7_capture_matrix(self):
        text = Path(__file__).with_name('set_hdr2_v0.c').read_text()
        start = text.index('static bool vdin_precise_gamut(')
        end = text.index('\n}', start) + 2
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
enum hdr_module_sel { VD1_HDR, VDIN0_HDR, VDIN1_HDR };
enum { MESON_CPU_MAJOR_ID_T7=7, HDR_SDR=2, HDR10P_SDR=4, HLG_SDR=16 };
static int cpu=7;
static int get_cpu_type(void) { return cpu; }
struct hdr_proc_mtx_param_s { int gmt_bit_mode, p_sel, mtx_gamut[9]; };
'''
        for name in ('ncl_2020_709', 'ncl_2020_709_8bit'):
            declaration = text.index('int ' + name + '[9]')
            fixture += text[declaration:text.index(';', declaration) + 1]
        assertions = r'''
int main(void) {
 struct hdr_proc_mtx_param_s parameters={.gmt_bit_mode=1,.p_sel=HDR_SDR};
 memcpy(parameters.mtx_gamut,ncl_2020_709_8bit,sizeof(parameters.mtx_gamut));
 assert(vdin_precise_gamut(VDIN0_HDR,&parameters));
 assert(vdin_precise_gamut(VDIN1_HDR,&parameters));
 assert(!vdin_precise_gamut(VD1_HDR,&parameters));
 parameters.p_sel=HLG_SDR;
 assert(vdin_precise_gamut(VDIN1_HDR,&parameters));
 parameters.p_sel=1;
 assert(!vdin_precise_gamut(VDIN1_HDR,&parameters));
 parameters.p_sel=HDR_SDR;
 parameters.mtx_gamut[0]++;
 assert(!vdin_precise_gamut(VDIN1_HDR,&parameters));
 parameters.mtx_gamut[0]--;
 parameters.gmt_bit_mode=0;
 assert(!vdin_precise_gamut(VDIN1_HDR,&parameters));
 parameters.gmt_bit_mode=1;
 cpu=6;
 assert(!vdin_precise_gamut(VDIN1_HDR,&parameters));
 for (int row=0;row<3;row++) {
  int sum=0;
  for (int column=0;column<3;column++) sum+=ncl_2020_709[row*3+column];
  assert(sum==2048);
 }
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / 'gamut.c', Path(directory) / 'gamut'
            source.write_text(fixture + text[start:end] + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_capture_curve_is_not_overwritten_by_vpp_tone_mapping(self):
        text = Path(__file__).with_name('set_hdr2_v0.c').read_text()
        start = text.index('static const int *hdr_sdr_gain(')
        end = text.index('\n}', start) + 2
        fixture = r'''
#include <assert.h>
#define HDR2_OOTF_LUT_SIZE 149
#define READ_ONCE(value) (value)
enum hdr_module_sel { VD1_HDR, VDIN0_HDR, VDIN1_HDR, DI_HDR };
static int oo_y_lut_hdr_sdr[149], vdin_oo_y_lut_hdr_sdr[149];
static int num_vdin_hdr_sdr_lut;
'''
        assertions = r'''
int main(void) {
 oo_y_lut_hdr_sdr[0]=1600;
 vdin_oo_y_lut_hdr_sdr[0]=3153;
 assert(hdr_sdr_gain(VDIN1_HDR)[0]==1600);
 num_vdin_hdr_sdr_lut=148;
 assert(hdr_sdr_gain(VDIN1_HDR)[0]==1600);
 num_vdin_hdr_sdr_lut=149;
 assert(hdr_sdr_gain(VDIN0_HDR)[0]==3153);
 assert(hdr_sdr_gain(VDIN1_HDR)[0]==3153);
 oo_y_lut_hdr_sdr[0]=800;
 assert(hdr_sdr_gain(VDIN1_HDR)[0]==3153);
 assert(hdr_sdr_gain(VD1_HDR)[0]==800);
 assert(hdr_sdr_gain(DI_HDR)[0]==800);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / 'curve.c', Path(directory) / 'curve'
            source.write_text(fixture + text[start:end] + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
