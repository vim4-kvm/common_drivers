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
