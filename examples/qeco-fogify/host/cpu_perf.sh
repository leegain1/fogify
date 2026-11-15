#!/bin/sh
# Fix CPU frequency / idle behaviour for the qeco-fogify measurements (Phase 4.5).
#   sudo sh host/cpu_perf.sh on    # performance governor + profile, no deep C-states on E-cores 8-15
#   sudo sh host/cpu_perf.sh off   # back to the defaults (powersave, balanced, all C-states)
#   sh host/cpu_perf.sh status
# Not persistent: a reboot restores the defaults.
set -e
E_CORES="8 9 10 11 12 13 14 15"
case "$1" in
on)
  for p in /sys/devices/system/cpu/cpufreq/policy*; do echo performance > "$p/scaling_governor"; done
  echo performance > /sys/firmware/acpi/platform_profile
  for c in $E_CORES; do        # keep POLL and C1E, disable C6 / C8 / C10 (wake-up latency 170+ us)
    for s in /sys/devices/system/cpu/cpu$c/cpuidle/state[2-9]; do [ -e "$s" ] && echo 1 > "$s/disable"; done
  done ;;
off)
  for p in /sys/devices/system/cpu/cpufreq/policy*; do echo powersave > "$p/scaling_governor"; done
  for p in /sys/devices/system/cpu/cpufreq/policy*; do echo balance_performance > "$p/energy_performance_preference"; done
  echo balanced > /sys/firmware/acpi/platform_profile
  for s in /sys/devices/system/cpu/cpu*/cpuidle/state*; do echo 0 > "$s/disable"; done ;;
status|*) ;;
esac
echo "governor: $(cat /sys/devices/system/cpu/cpu8/cpufreq/scaling_governor)," \
     "EPP: $(cat /sys/devices/system/cpu/cpu8/cpufreq/energy_performance_preference)," \
     "profile: $(cat /sys/firmware/acpi/platform_profile)"
for c in $E_CORES; do
  printf "cpu%s disabled C-states:" "$c"
  for s in /sys/devices/system/cpu/cpu$c/cpuidle/state*; do [ "$(cat $s/disable)" = 1 ] && printf " %s" "$(cat $s/name)"; done
  echo
done
