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
 for (int uhd=0;uhd<2;uhd++) {
  device.index=secondary; device.v4l2_port[0]=hdmi;
  unsigned int count=secondary && hdmi && !uhd ? 7 : 5;
  for (unsigned int i=0;i<9;i++) {
   struct v4l2_frmivalenum f={.index=i,.width=uhd?3840:1920,.height=uhd?2160:1080};
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


if __name__ == '__main__':
    unittest.main()
