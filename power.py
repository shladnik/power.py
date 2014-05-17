#!/usr/bin/python2
import os
import actmon
import threading
import subprocess
import time
import datetime
import pyosd

event = threading.Event()
user = 'stefan'


#
# Battery class
#
class Battery():
  def level(self):
    self.update()
    return self._level

  def time2full(self):
    self.update()
    return self._time2full

  def time2empty(self):
    self.update()
    return self._time2empty

  def parse_power_supply(self):
    def parse_var(l):
      prefix = 'POWER_SUPPLY_'
      l = l.split(prefix, 1)[1]
      l = l.rstrip()
      name, val = l.split('=', 1)
      if val.isdigit(): val = int(val)
      return name, val
    return { k : v for k, v in ( parse_var(l) for l in open('/sys/class/power_supply/' + 'BAT1' + '/uevent', 'r') ) }

  def update(self):
    info = self.parse_power_supply()
    self._level = float(info['CHARGE_NOW']) / info['CHARGE_FULL']
    if info['CURRENT_NOW']:
      if   info['STATUS'] == 'Discharging':
        self._time2empty = datetime.timedelta(hours = float(info['CHARGE_NOW']) / info['CURRENT_NOW'])
        self._time2full  = None
      elif info['STATUS'] ==    'Charging':
        self._time2empty = None
        self._time2full  = datetime.timedelta(hours = float(info['CHARGE_FULL'] - info['CHARGE_NOW']) / info['CURRENT_NOW'])
      else:
        assert info['STATUS'] == 'Full'
    else:
      self._time2full  = None
      self._time2empty = None

#
# ACPI events
#
def acpiListener():
  p = subprocess.Popen('acpi_listen', stdout=subprocess.PIPE)
  while 1:
    print(p.stdout.readline(),)
    event.set()
      
t = threading.Thread(target = acpiListener, name = 'acpiListenerThread')
t.daemon = True
t.start()


#
# Helping functions
#

def wakealarmSet(when):
  if type(when) == datetime.timedelta:
    when = datetime.datetime.now() + when
  open('/sys/class/rtc/rtc0/wakealarm', 'w').write("0") # needs to be cleared first
  open('/sys/class/rtc/rtc0/wakealarm', 'w').write(when.strftime("%s"))
  return when

def wakealarmGet():
  return open('/sys/class/rtc/rtc0/wakealarm', 'r').read()

def brightnessSet(val):
  b_max = int(open('/sys/class/backlight/radeon_bl0/max_brightness', 'r').read(), 10)
  open('/sys/class/backlight/radeon_bl0/brightness', 'w').write(str(int(round(b_max * val))))

def brightnessGet():
  b_max = float(int(open('/sys/class/backlight/radeon_bl0/max_brightness'   , 'r').read(), 10))
  b_act = float(int(open('/sys/class/backlight/radeon_bl0/actual_brightness', 'r').read(), 10))
  return b_act / b_max

def screenOff():
  subprocess.call(['su', '-c', 'DISPLAY=:0 XAUTHORITY=/home/stefan/.Xauthority xset dpms force off', 'stefan'])

def diskSpeedup():
  subprocess.call(['sync'])
  open('/proc/sys/vm/drop_caches', 'w').write('3')

def laptop_mode(delay=900, lm_settings=[2, 60, 1]):
  open('/proc/sys/vm/laptop_mode'              , 'w').write(str(lm_settings[0]))
  open('/proc/sys/vm/dirty_ratio'              , 'w').write(str(lm_settings[1]))
  open('/proc/sys/vm/dirty_background_ratio'   , 'w').write(str(lm_settings[2]))
  open('/proc/sys/vm/dirty_expire_centisecs'   , 'w').write(str(    1 * 100))
  open('/proc/sys/vm/dirty_writeback_centisecs', 'w').write(str(delay * 100))
  subprocess.call(['mount', '-o', 'remount,commit=' + str(delay), '/dev/sda1'])
  subprocess.call(['mount', '-o', 'remount,commit=' + str(delay), '/dev/sda6'])
  hdparm()

def hdparm():
  device='/dev/sda'
  S=4
  B=1
  subprocess.call(['hdparm', '-S' + str(S), '-B' + str(B), device ])
  
def osd(text, size=20):
  #http://en.wikipedia.org/wiki/X_logical_font_description
  global p # Without that OSD disappears immediately
  #font="-misc-fixed-medium-r-normal--20-140-100-100-c-100-iso8859-1"
  font="-misc-fixed-medium-r-normal--" + str(size) + "-*-*-*-*-*-*"
  p = pyosd.osd(font=font, colour='#BBBBBB', timeout=2, pos=2, offset=0, hoffset=0, shadow=int(size*5/8), align=1, lines=1, noLocale=False)
  p.display(text)

#
# Tasks
#

def freeze():
  ''' Not usefull for me because it only wakes on power button '''
  open('/sys/power/state', 'w').write('freeze')

def mem():
  open('/sys/power/state', 'w').write('mem')

def disk():
  diskSpeedup()
  open('/sys/power/disk',  'w').write('platform')
  open('/sys/power/state', 'w').write('disk')
  hdparm()

def hybrid():
  diskSpeedup()
  open('/sys/power/disk' , 'w').write('suspend')
  open('/sys/power/state', 'w').write('disk')

def freezeDelayMem(delay = datetime.timedelta(minutes = 10)):
  wakealarmSet(delay)
  freeze()
  if not wakealarmGet():
    mem()

def memDelayDisk(delay = datetime.timedelta(minutes = 20)):
  wakealarmSet(delay)
  mem()
  if not wakealarmGet():
    disk()

def brightnessMul(f):
  brightnessSet(brightnessGet() * f)

def blink(off = 0.1, on = 0.1, repeat = 1):
  for i in range(repeat):
    curr = open('/sys/class/backlight/radeon_bl0/actual_brightness').read()
    open('/sys/class/backlight/radeon_bl0/brightness', 'w').write('0')
    time.sleep(off)
    open('/sys/class/backlight/radeon_bl0/brightness', 'w').write(curr)
    time.sleep(on)
  time.sleep(1)

def lock():
  screenOff()
  subprocess.Popen(['su', '-c', 'DISPLAY=:0 XAUTHORITY=/home/stefan/.Xauthority slock', 'stefan'])

def governorSet(governor = 'ondemand'):
  print("Setting governor:", governor)
  open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor', 'w').write(governor)

def osdBattery():
    level = int(battery.level() * 100)
    time2empty = battery.time2empty()
    if time2empty:
        osd(str(level) + "% (" + str(time2empty) + ")", size = max(20, 100.0 * (3600 - time2empty.total_seconds()) / 3600))
    else:
        osd(str(level) + "%")

backup_p = None
backup_p_last = datetime.datetime.now() - datetime.timedelta(hours=24)
def backup():
  global backup_p
  global backup_p_last
  now = datetime.datetime.now()
  if now - backup_p_last > datetime.timedelta(hours=24) and\
     (backup_p == None or backup_p.poll() != None):
    backup_p = subprocess.Popen(['/root/backup.py'])
    backup_p_last = now


#
# Task lists - discrete states (Lid, AC) dependant
#

tasksOnBatt = (
  lambda: governorSet('powersave'),
)

tasksOnAC = (
)

tasksOnLidClose = (
  lambda: lock(),
)

tasksOnLidOpen = (
)

tasksOnBattLidClose = tasksOnBatt + tasksOnLidClose + (
  lambda: memDelayDisk(),
)

tasksOnBattLidOpen  = tasksOnBatt + tasksOnLidOpen  + (
)

tasksOnACLidClose   = tasksOnAC   + tasksOnLidClose + (
  lambda: governorSet('powersave'),
)

tasksOnACLidOpen    = tasksOnAC   + tasksOnLidOpen  + (
  lambda: governorSet('ondemand'),
)

#
# Task lists - idle time dependant
#

tasksIdleCommon = (
  ( datetime.timedelta(minutes = 1.0), lambda: brightnessMul(0.98) ),
  ( datetime.timedelta(minutes = 2.0), lambda: brightnessMul(0.98) ),
  ( datetime.timedelta(minutes = 3.0), lambda: brightnessMul(0.98) ),
  ( datetime.timedelta(minutes = 4.0), lambda: screenOff()        ),
  ( datetime.timedelta(minutes = 4.9), lambda: lock()             ),
)

tasksIdleBatt = tasksIdleCommon + (
  ( datetime.timedelta(minutes = 5.0), lambda: memDelayDisk() ),
)

tasksIdleAC = tasksIdleCommon + (
  ( datetime.timedelta(hours   = 1.0), lambda: backup() ),
)

#
# Task lists - battery level dependant
#

tasksBattLevel = (
#  # Warnings
  ( datetime.timedelta(minutes = 60.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes = 50.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes = 40.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes = 30.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes = 25.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes = 20.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes = 15.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes = 10.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  9.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  8.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  7.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  6.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  5.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  4.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  3.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  2.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  1.0), lambda: osdBattery() ),
  ( datetime.timedelta(minutes =  0.0), lambda: osdBattery() ),
  # Other batery level dependand stuff 
  ( datetime.timedelta(minutes =  5.0), lambda: lock()),
  ( datetime.timedelta(minutes =  5.0), lambda: disk()),
)

laptop_mode()
# AHCI saving
open('/sys/class/scsi_host/host0/link_power_management_policy', 'w').write('min_power')
# Audio saving
#open('/sys/module/snd_hda_intel/parameters/power_save'           , 'w').write('10')
#open('/sys/module/snd_hda_intel/parameters/power_save_controller', 'w').write('Y')
# Video saving
open('/sys/class/drm/card0/device/power_method' , 'w').write('profile')
open('/sys/class/drm/card0/device/power_profile', 'w').write('low')
# USB saving
usb_path = '/sys/bus/usb/devices/'
for i in os.listdir(usb_path):
  if i[0:3] == 'usb':
    path = usb_path + i + '/power/'
    open(path + 'wakeup'              , 'w').write('disabled')
    open(path + 'control'             , 'w').write('auto')
    open(path + 'autosuspend_delay_ms', 'w').write('1000')

battery = Battery()

acPrev  = None
lidPrev = None
idlePrev = datetime.timedelta(0)

iIdle = 0
iBatt = 0

while 1:
  # State tasks
  ac  = '1'    in open("/sys/class/power_supply/ACAD/online").read()
  lid = 'open' in open('/proc/acpi/button/lid/LID/state', 'r').read()
  print("AC:", ac, "LID", lid)
  
  if ac != acPrev or lid != lidPrev:
    if   not ac and not lid: tasksOn = tasksOnBattLidClose
    elif not ac and     lid: tasksOn = tasksOnBattLidOpen
    elif     ac and not lid: tasksOn = tasksOnACLidClose
    else                   : tasksOn = tasksOnACLidOpen
   
    for t in tasksOn: t()
    
    if not ac: osdBattery()
  
  
  # Battery tasks
  if ac:
    iBatt = 0
  else:
    time2empty = battery.time2empty()
    if time2empty:
      print("time2empty:", str(time2empty), iBatt)
      tasksBL = sorted(tasksBattLevel, cmp=lambda x, y: cmp(x[0], y[0]), reverse=True)
      for iBatt in range(iBatt, len(tasksBL)):
        t = tasksBL[iBatt]
        if time2empty > t[0]: break;
        t[1]()


  # Idle tasks
  idle = datetime.timedelta(milliseconds = actmon.get_idle_time())
  print("idle:", str(idle))
  
  if idle < idlePrev or ac != acPrev: iIdle = 0
  tasksIdle = sorted(( tasksIdleBatt, tasksIdleAC )[ac], cmp = lambda x, y: cmp(x[0], y[0]))

  for iIdle in range(iIdle, len(tasksIdle)):
    t = tasksIdle[iIdle]
    if idle < t[0]: break;
    t[1]()

  idlePrev = idle


  acPrev   = ac
  lidPrev  = lid
  idlePrev = idle

  event.wait(timeout = 5)
  event.clear()



"""
Notes

Battery:
  - powersave governor?
  - laptop mode?
  - 4  mins - dim
  Lid:
  - 5  mins - lock
  - 5  mins - mem -> 30 -> disk

AC:
  - 4 mins - dim
  - 5 mins - lock
  - 30 mins - backup
  Lid: (silence)
    - powersave governor?
    - laptop mode?

Sleep button: disk


Boolean states
  * AC / Batt
  * Lid
Idle time
Battery level
"""
