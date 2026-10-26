import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).with_name('vdin_drv.c').read_text()


def function(name):
    start = SOURCE.index('\n' + name + '(') if '\n' + name + '(' in SOURCE else SOURCE.index(name + '(')
    start = SOURCE.rfind('\n', 0, start) + 1
    brace = SOURCE.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end]


class SecondaryHdmiTest(unittest.TestCase):
    def test_secondary_geometry_overrides_stale_primary_destination(self):
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
typedef unsigned int u32;
enum { VDIN_SACALE_4096_2_3840=1, VDIN_CUTWIN_4096_2_3840=2,
       TVIN_SIG_FMT_HDMI_4096_2160_00HZ=10, VDIN_WORK_MD_V4L=1,
       VDIN_FLAG_MANUAL_CONVERSION=4 };
#define IS_HDMI_SRC(port) ((port)==1)
struct tvin_format_s { unsigned int h_active, v_active; };
struct vdin_dev_s {
 struct tvin_format_s *fmt_info_p;
 struct { u32 vdin0_max_w_h; } *dtdata;
 int vdin_function_sel, work_mode, flags;
 bool shared_hdmi_frontend;
 struct { int port, dest_width, dest_height; struct { int fmt; } info; } parm;
 struct { u32 scaling4w, scaling4h, decimation_ratio, dest_cfmt, hs, he, vs, ve; } prop;
 struct { int hw5_ctl, dw_out_w, dw_out_h, dw_dfmt; } dv_hw5;
 struct { u32 scaling4w, scaling4h, dest_cfmt;
          struct { u32 hs, he, vs, ve; } cutwin; } debug;
 struct { struct { struct { unsigned int width, height; } pix_mp; } fmt; } v4l2_fmt;
};
'''
        assertions = r'''
int main(void) {
 struct tvin_format_s timing={2560,1440};
 struct vdin_dev_s device={.fmt_info_p=&timing, .shared_hdmi_frontend=true,
                          .work_mode=VDIN_WORK_MD_V4L};
 device.dtdata=&(typeof(*device.dtdata)){0};
 device.parm.port=1; device.parm.dest_width=3840; device.parm.dest_height=2160;
 /* The old UHD destination must not enable the vertical scaler and its
  * 1920-pixel line-buffer clamp for native QHD or ultrawide capture. */
 const unsigned int sizes[][2]={{2560,1440},{3440,1440},{2560,1080},
                              {3840,2160},{1280,720},{2560,1440}};
 for (unsigned int i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++) {
  device.v4l2_fmt.fmt.pix_mp.width=sizes[i][0];
  device.v4l2_fmt.fmt.pix_mp.height=sizes[i][1];
  vdin_scale_and_cutwin_handle(&device);
  assert(device.prop.scaling4w==sizes[i][0]);
  assert(device.prop.scaling4h==sizes[i][1]);
 }
 device.shared_hdmi_frontend=false;
 vdin_scale_and_cutwin_handle(&device);
 assert(device.prop.scaling4w==3840 && device.prop.scaling4h==2160);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / 'geometry.c', Path(directory) / 'geometry'
            source.write_text(fixture + function('vdin_scale_and_cutwin_handle') + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_live_secondary_updates_hdr_matrix_range_and_depth_at_frame_boundary(self):
        fixture = r'''
#include <assert.h>
#include <stdbool.h>
enum { VDIN_FLAG_DEC_STARTED=1, VDIN_FLAG_RDMA_ENABLE=2,
       HDR_STATE_NULL=0, EOTF_HDR=1, EOTF_SMPTE_ST_2048=2, EOTF_HLG=3 };
#define READ_ONCE(value) (value)
struct tvin_sig_property_s {
 int color_format, color_fmt_range, colordepth;
 bool vdin_hdr_flag;
 struct { int hdr_state; struct { int eotf; } hdr_data; } hdr_info;
};
struct tvin_frontend_s;
struct tvin_state_machine_ops_s {
 void (*get_sig_property)(struct tvin_frontend_s *, struct tvin_sig_property_s *, int);
};
struct tvin_frontend_s { struct tvin_state_machine_ops_s *sm_ops; };
struct vdin_dev_s {
 int flags, port_type, addr_offset, format_convert, full_pack, source_bitdepth, h_active, bt_path;
 bool shared_hdmi_frontend, hdr_reload_pending, hdr_sdr_output;
 struct tvin_frontend_s *frontend;
 struct tvin_sig_property_s prop, pre_prop;
 struct { int port; } parm;
};
static struct vdin_dev_s *vdin_devp[2];
static struct tvin_sig_property_s source;
static int matrix_updates, top_updates;
static bool exchange(bool *value, bool replacement)
{ bool previous=*value; *value=replacement; return previous; }
#define xchg exchange
static void get_property(struct tvin_frontend_s *frontend,
                         struct tvin_sig_property_s *property, int port)
{ (void)frontend; (void)port; *property=source; }
static void vdin_get_format_convert(struct vdin_dev_s *device) { (void)device; }
static void vdin_set_matrix(struct vdin_dev_s *device)
{ matrix_updates++; device->hdr_sdr_output=device->prop.vdin_hdr_flag; }
static void vdin_set_bitdepth(struct vdin_dev_s *device) { (void)device; }
static void vdin_source_bitdepth_reinit(struct vdin_dev_s *device) { (void)device; }
static void vdin_set_wr_ctrl_vsync(struct vdin_dev_s *device, int offset,
                                 int format, int packed, int depth, int flags)
{ (void)device; (void)offset; (void)format; (void)packed; (void)depth; (void)flags; }
static void vdin_set_top(struct vdin_dev_s *device, int offset, int port,
                        int color, int width, int path)
{ (void)device; (void)offset; (void)port; (void)color; (void)width; (void)path; top_updates++; }
'''
        assertions = r'''
int main(void) {
 struct tvin_state_machine_ops_s ops={get_property};
 struct tvin_frontend_s frontend={&ops};
 struct vdin_dev_s primary={0}, secondary={.frontend=&frontend};
 vdin_devp[0]=&primary;
 assert(!vdin_update_shared_hdmi(&secondary));
 secondary.shared_hdmi_frontend=true;
 assert(vdin_update_shared_hdmi(&secondary) && matrix_updates==0);
 primary.flags=VDIN_FLAG_DEC_STARTED;
 source.color_format=1; source.colordepth=10;
 source.hdr_info.hdr_state=1; source.hdr_info.hdr_data.eotf=EOTF_SMPTE_ST_2048;
 assert(vdin_update_shared_hdmi(&secondary) && secondary.hdr_sdr_output);
 assert(!vdin_update_shared_hdmi(&secondary) && matrix_updates==1);
 source.color_format=2; source.hdr_info.hdr_state=HDR_STATE_NULL;
 source.hdr_info.hdr_data.eotf=0;
 assert(vdin_update_shared_hdmi(&secondary) && !secondary.hdr_sdr_output);
 assert(!vdin_update_shared_hdmi(&secondary));
 source.hdr_info.hdr_state=1; source.hdr_info.hdr_data.eotf=EOTF_SMPTE_ST_2048;
 assert(vdin_update_shared_hdmi(&secondary) && secondary.hdr_sdr_output);
 source.hdr_info.hdr_data.eotf=EOTF_HLG;
 assert(vdin_update_shared_hdmi(&secondary));
 source.color_fmt_range=1;
 assert(vdin_update_shared_hdmi(&secondary));
 source.colordepth=12;
 assert(vdin_update_shared_hdmi(&secondary));
 secondary.hdr_reload_pending=true;
 assert(vdin_update_shared_hdmi(&secondary) && !secondary.hdr_reload_pending);
 assert(!vdin_update_shared_hdmi(&secondary));
 assert(matrix_updates==7 && top_updates==7 && primary.flags==VDIN_FLAG_DEC_STARTED);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / 'follow.c', Path(directory) / 'follow'
            source.write_text(fixture + function('vdin_update_shared_hdmi') + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_secondary_lifecycle_never_reopens_or_closes_primary_receiver(self):
        fixtures = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
enum tvin_port_e { TVIN_PORT_NULL, HDMI1, HDMI2 };
enum { VDIN_HW_T7=7, VDIN_FLAG_DEC_STARTED=1, VDIN_FLAG_DEC_OPENED=2,
       TVIN_SIG_STATUS_NULL=0, TVIN_SIG_FMT_NULL=0, VDIN_PUT_INTERVAL=1,
       TVIN_SIG_CHG_CLOSE_FE=4 };
#define IS_HDMI_SRC(port) ((port)==HDMI1 || (port)==HDMI2)
#define IS_TVAFE_SRC(port) false
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
struct tvin_frontend_s;
struct decoder { int (*open)(struct tvin_frontend_s *, enum tvin_port_e, int);
                 void (*close)(struct tvin_frontend_s *, int); };
struct tvin_frontend_s { struct decoder *dec_ops; };
struct vdin_dev_s {
 struct { int hw_ver; } *dtdata;
 int index, flags, prop, pre_prop, port_type;
 bool shared_hdmi_frontend;
 struct tvin_frontend_s *frontend;
 struct { enum tvin_port_e port; struct { int status, fmt; } info; } parm;
 struct { void (*function)(void *); int expires; } timer;
 struct { int event_sts; } event_info;
};
static struct vdin_dev_s *vdin_devp[2];
static int opened, closed, timers, jiffies;
static int receiver_open(struct tvin_frontend_s *fe, enum tvin_port_e port, int type)
{ (void)fe; (void)port; (void)type; opened++; return 0; }
static void receiver_close(struct tvin_frontend_s *fe, int type)
{ (void)fe; (void)type; closed++; }
static struct decoder ops={ receiver_open, receiver_close };
static struct tvin_frontend_s frontend={ &ops };
static struct tvin_frontend_s *tvin_get_frontend(enum tvin_port_e port, int index)
{ (void)port; (void)index; return &frontend; }
static void tvin_smr_init(int index) { (void)index; }
static void vdin_timer_func(void *timer) { (void)timer; }
#define add_timer(timer) ((void)(timer), timers++)
#define del_timer_sync(timer) ((void)(timer), timers--)
static void vdin_send_event(struct vdin_dev_s *device, int event)
{ (void)device; (void)event; }
'''
        assertions = r'''
int main(void) {
 struct vdin_dev_s primary={0}, secondary={0};
 primary.dtdata=secondary.dtdata=&(typeof(*primary.dtdata)){ .hw_ver=VDIN_HW_T7 };
 primary.index=0; secondary.index=1;
 vdin_devp[0]=&primary; vdin_devp[1]=&secondary;
 assert(vdin_open_fe(HDMI1,0,&primary)==0);
 assert(opened==1 && timers==1);
 assert(vdin_open_fe(HDMI1,0,&secondary)==-ENOLINK);
 assert(secondary.frontend==NULL && secondary.parm.port==TVIN_PORT_NULL);
 primary.flags|=VDIN_FLAG_DEC_STARTED;
 assert(vdin_open_fe(HDMI2,0,&secondary)==-ENOLINK);
 assert(secondary.frontend==NULL && secondary.parm.port==TVIN_PORT_NULL);
 assert(vdin_open_fe(HDMI1,0,&secondary)==0);
 assert(secondary.shared_hdmi_frontend && opened==1 && timers==1);
 vdin_close_fe(&secondary);
 assert(closed==0 && timers==1 && !secondary.shared_hdmi_frontend);
 assert(primary.flags & VDIN_FLAG_DEC_STARTED);
 vdin_close_fe(&primary);
 assert(closed==1 && timers==0);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'secondary.c'
            binary = Path(directory) / 'secondary'
            source.write_text(fixtures + function('vdin_open_fe') + '\n' + function('vdin_close_fe') + assertions)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
