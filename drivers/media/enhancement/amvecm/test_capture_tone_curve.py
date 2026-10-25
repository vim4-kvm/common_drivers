import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class CaptureCurveTest(unittest.TestCase):
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
