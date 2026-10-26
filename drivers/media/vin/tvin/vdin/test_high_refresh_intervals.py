"""Compile the actual VDIN interval ioctl; negotiation must expose HDMI 1080p120."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class IntervalsTest(unittest.TestCase):
    def test_hdmi_negotiation_and_legacy_limits(self):
        source = Path(__file__).with_name('vdin_v4l2_if.c').read_text()
        table = source[source.index('static struct v4l2_fract fract_discrete[]'):]
        table = table[:table.index('};') + 2]
        function = source[source.index('static int vdin_vidioc_enum_frameintervals('):]
        function = function[:function.index('\n}\n') + 3]
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stddef.h>
#include <linux/videodev2.h>
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define IS_HDMI_SRC(port) ((port)==1)
struct vdin_dev_s { int index; int v4l2_port[1]; } device;
struct file {};
#define video_drvdata(file) (&device)
'''
        assertions = r'''
int main(void) {
 const unsigned int rates[] = {24,25,30,50,60,100,120};
 for (int secondary=0;secondary<2;secondary++)
 for (int hdmi=0;hdmi<2;hdmi++)
 for (int mode=0;mode<4;mode++) {
  const unsigned int widths[]={1920,2560,3440,3840};
  const unsigned int heights[]={1080,1440,1440,2160};
  device.index=secondary; device.v4l2_port[0]=hdmi;
  unsigned int count=secondary && hdmi && mode<2 ? 7 : 5;
  for (unsigned int i=0;i<9;i++) {
   struct v4l2_frmivalenum f={.index=i,.width=widths[mode],.height=heights[mode]};
   int result=vdin_vidioc_enum_frameintervals(0,0,&f);
   if (i>=count) assert(result==-EINVAL);
   else { assert(!result); assert(f.type==V4L2_FRMIVAL_TYPE_DISCRETE);
          assert(f.discrete.numerator==1 && f.discrete.denominator==rates[i]); }
  }
 }
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            code, binary = Path(temporary) / 'intervals.c', Path(temporary) / 'intervals'
            code.write_text(fixture + table + function + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                            '-Wno-sign-compare', str(code), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_native_hdmi_sizes_are_negotiable(self):
        source = Path(__file__).with_name('vdin_v4l2_if.c').read_text()
        tables = []
        for declaration in ['static struct v4l2_frmsize_discrete vdin_v4l2_frmsize_dis[]',
                            'static const struct v4l2_frmsize_discrete vdin_hdmi_frmsizes[]']:
            table = source[source.index(declaration):]
            tables.append(table[:table.index('};') + 2])
        function = source[source.index('static int vdin_vidioc_enum_framesizes('):]
        function = function[:function.index('\n}\n') + 3]
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stddef.h>
#include <linux/videodev2.h>
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define IS_HDMI_SRC(port) ((port)==1)
struct vdin_dev_s { int index; int v4l2_port[1]; } device;
struct file {};
#define video_drvdata(file) (&device)
struct vdin_v4l2_pix_fmt { unsigned int fourcc; };
static struct vdin_v4l2_pix_fmt pix_formats[] = {{V4L2_PIX_FMT_NV21}};
'''
        assertions = r'''
int main(void) {
 for (int secondary=0; secondary<2; secondary++)
 for (int hdmi=0; hdmi<2; hdmi++) {
  device.index=secondary; device.v4l2_port[0]=hdmi;
  bool found_qhd=false, found_wide=false, found_ultrawide=false;
  unsigned int i;
  for (i=0; i<20; i++) {
   struct v4l2_frmsizeenum f={.index=i,.pixel_format=V4L2_PIX_FMT_NV21};
   int result=vdin_vidioc_enum_framesizes(0,0,&f);
   if (result) { assert(result==-EINVAL); break; }
   assert(f.type==V4L2_FRMSIZE_TYPE_DISCRETE);
   found_qhd |= f.discrete.width==2560 && f.discrete.height==1440;
   found_wide |= f.discrete.width==2560 && f.discrete.height==1080;
   found_ultrawide |= f.discrete.width==3440 && f.discrete.height==1440;
  }
  assert(i<20);
  assert(found_qhd == (secondary && hdmi));
  assert(found_wide == (secondary && hdmi));
  assert(found_ultrawide == (secondary && hdmi));
  struct v4l2_frmsizeenum bad={.pixel_format=V4L2_PIX_FMT_RGB24};
  assert(vdin_vidioc_enum_framesizes(0,0,&bad)==-EINVAL);
 }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            code, binary = Path(temporary) / 'sizes.c', Path(temporary) / 'sizes'
            code.write_text(fixture + '\n'.join(tables) + function + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                            '-Wno-sign-compare', str(code), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
