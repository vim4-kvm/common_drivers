import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class HdmiMetadataTest(unittest.TestCase):
    def test_native_hdmi_preserves_zero_and_partial_static_metadata(self):
        text = Path(__file__).with_name('amcsc.c').read_text()
        start = text.index('static void amvecm_copy_hdmi_metadata(')
        brace = text.index('{', start)
        end, depth = brace + 1, 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#define VD_PATH_MAX 3
#define PROC_BYPASS 1
struct vframe_master_display_colour_s {
 unsigned present_flag, primaries[3][2], white_point[2], luminance[2];
 struct { unsigned present_flag, max_content, max_pic_average; } content_light_level;
};
struct master_display_info_s {
 unsigned features, present_flag, primaries[3][2], white_point[2], luminance[2];
 unsigned max_content, max_frame_average;
};
static bool customer_master_display_en, customer_hdmi_display_en;
static struct vframe_master_display_colour_s cur_master_display_colour[VD_PATH_MAX];
static struct vframe_master_display_colour_s hdmi_input_metadata[VD_PATH_MAX];
static bool hdmi_input_metadata_valid[VD_PATH_MAX];
static unsigned hdr_process_mode[VD_PATH_MAX];
'''
        assertions = r'''
int main(void) {
 struct master_display_info_s output={ .features=16<<8, .luminance={1000,50},
                                       .primaries={{8500,39850}} };
 hdmi_input_metadata_valid[0]=true;
 hdr_process_mode[0]=PROC_BYPASS;
 hdmi_input_metadata[0].present_flag=1;
 amvecm_copy_hdmi_metadata(&output, &cur_master_display_colour[0]);
 assert(output.primaries[0][0]==0 && output.luminance[0]==0 && output.luminance[1]==0);
 hdmi_input_metadata[0].luminance[0]=1200;
 hdmi_input_metadata[0].content_light_level.max_content=900;
 hdmi_input_metadata[0].content_light_level.max_pic_average=0;
 amvecm_copy_hdmi_metadata(&output, &cur_master_display_colour[0]);
 assert(output.luminance[0]==1200 && output.max_content==900 && output.max_frame_average==0);
 output.features=18<<8;
 amvecm_copy_hdmi_metadata(&output, &cur_master_display_colour[0]);
 assert(output.luminance[0]==1200);
 output.luminance[0]=77;
 output.features=1<<8;
 amvecm_copy_hdmi_metadata(&output, &cur_master_display_colour[0]);
 assert(output.luminance[0]==77);
 output.features=16<<8;
 hdr_process_mode[0]=2;
 amvecm_copy_hdmi_metadata(&output, &cur_master_display_colour[0]);
 assert(output.luminance[0]==77);
 hdr_process_mode[0]=PROC_BYPASS;
 customer_hdmi_display_en=true;
 amvecm_copy_hdmi_metadata(&output, &cur_master_display_colour[0]);
 assert(output.luminance[0]==77);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / 'metadata.c', Path(directory) / 'metadata'
            source.write_text(fixture + text[start:end] + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
