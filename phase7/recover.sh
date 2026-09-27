#!/bin/bash
# Fast recovery after VM reboot: reinstall apt deps from persistent cache, resume build.
# /home persists; /usr is wiped; /var/cache/apt/archives persists.
set -e
LOG=~/pgrev/phase7/logs/recover.log
echo "=== recovery $(date -u) ===" >> $LOG
cd /var/cache/apt/archives
sudo -n dpkg -i *.deb >> $LOG 2>&1 || true
sudo -n dpkg --configure -a >> $LOG 2>&1 || true
echo "dpkg done: $(dpkg -l libboost-dev 2>/dev/null | tail -1 | awk '{print $1}')" >> $LOG
# resume build (openroad binary only, skip test executables)
cd ~/pgrev/phase7/openroad-src/build
setsid nohup make openroad -j2 >> ~/pgrev/phase7/logs/make-recover.log 2>&1 < /dev/null &
echo "build resumed pid $!" >> $LOG
echo "RECOVERY_DONE"
