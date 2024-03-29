#!/usr/bin/env python3

import json
import platform
import subprocess
import shutil
import datetime
import os
import sys
import psutil
import threading
import time
import re


class NewThread(threading.Thread):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={}):
        threading.Thread.__init__(self, group, target, name, args, kwargs)

    def run(self):
        if self._target != None:
            self._return = self._target(*self._args, **self._kwargs)
            

    def join(self, *args):
        threading.Thread.join(self, *args)
        return self._return


def get_lines_count(com):
    s = subprocess.run(['bash', '-c', com],
                       stdout=subprocess.PIPE).stdout.decode()
    return s.count("\n")


def parse_serives_list(stdout):
    stdout = stdout.replace('\t', ' ').strip().split('\n')
    svs = []
    for service in stdout:
        service = list(filter(None, service.split(" ")))
        if len(service) > 4:
            svs.append(
                {
                    "unit": service[0],
                    "load": service[1],
                    "active": service[2],
                    "sub": service[3],
                    "description": " ".join(service[4:])
                }
            )
    return svs


def format_timedelta(seconds):
    days = int(seconds / 86400)
    hours = int((seconds % 86400) / 3600)
    minutes = int(((seconds % 86400) % 3600) / 60)

    if days:
        result = f"{days}d {hours}h {minutes}m"
    elif hours:
        result = f"{hours}h {minutes}m"
    else:
        result = f"{minutes}m"

    return result


def get_text_from_brackets(str):
    result = []
    for m in re.finditer(r'"(.*?)"', str):
        result.append(m.group(1))
    return result


def get_os_release():
    try:
        return platform.freedesktop_os_release()
    except:
        try:
            f = open("/etc/os-release")
            obj = {}
            for line in f.read().strip().replace('"', '').split("\n"):
                obj[line.split('=')[0]] = line.split('=')[1]
            return obj
        except:
            raise OSError


def get_processor_name():
    if platform.system() == "Windows":
        return platform.processor()
    elif platform.system() == "Darwin":
        return subprocess.check_output("sysctl -n machdep.cpu.brand_string").strip()
    elif platform.system() == "Linux":
        command = "cat /proc/cpuinfo"
        all_info = subprocess.check_output(
            command, shell=True).decode().strip()
        for line in all_info.split("\n"):
            if "model name" in line:
                return re.sub(".*model name.*:", "", line, 1)
    return ""


def get_cpu_percent(interval=1):
    cpu = psutil.cpu_percent(interval=interval)
    return cpu

def get_full_report(cpu_percent_interval=1):
    report = {}

    # notice, warning, alert, alarm
    report["problems"] = []

    ######################################
    #                                    #
    #     OPERATING SYSTEM AND STUFF     #
    #                                    #
    ######################################

    report["system"] = {}
    report["system"]["name"] = platform.system()
    report["system"]["release"] = platform.release()
    report["system"]["platform"] = platform.platform()

    try:
        report["system"]["distro"] = get_os_release()["NAME"]
    except OSError:
        pass

    try:
        report["system"]["libc"] = " ".join(platform.libc_ver())
    except OSError:
        pass

    report["system"]["python"] = platform.python_version()
    report["system"]["memory"] = psutil.virtual_memory()._asdict()
    report["system"]["swap"] = psutil.swap_memory()._asdict()

    cpufreq = psutil.cpu_freq()

    report["system"]["cpu"] = {
        "name": get_processor_name(),
        "arch": platform.machine(),
        "threads": psutil.cpu_count(logical=True),
        "cores": psutil.cpu_count(logical=False),
        "freq_min": cpufreq.min,
        "freq_max": cpufreq.max,
        "freq_current": round(cpufreq.current, 1)
    }

    get_cpu_percent_thread = NewThread(target=get_cpu_percent, args=(cpu_percent_interval, ))
    get_cpu_percent_thread.start()

    report["system"]["mountpoints"] = []

    for part in psutil.disk_partitions(all=True):
        try:
            part = part._asdict()
            part["usage"] = psutil.disk_usage(part["mountpoint"])._asdict()
            report["system"]["mountpoints"].append(part)
        except PermissionError:
            pass

    report["system"]["pci"] = []
    try:
        s = subprocess.run(['lspci', '-mm'],
                           stdout=subprocess.PIPE).stdout.decode().strip().split('\n')
        for line in s:
            lst = []
            lst.append(line.split()[0])
            for a in get_text_from_brackets(line):
                lst.append(a)

            report["system"]["pci"].append(lst)
    except:
        pass

    report["system"]["usb"] = []
    try:
        s = subprocess.run(['lsusb'],
                           stdout=subprocess.PIPE).stdout.decode().strip().split('\n')
        for line in s:
            line = line.split()
            lst = [line[1], line[3].replace(
                ':', ''), line[5], " ".join(line[6:])]

            report["system"]["usb"].append(lst)
    except:
        pass

    try:
        s = json.loads(subprocess.run(['lsblk', '--json'],
                                      stdout=subprocess.PIPE).stdout.decode())

        report["system"]["blockdevices"] = s["blockdevices"]
    except:
        pass

    pkgs = []

    pairs = [
        ["kiss", "kiss l"],
        ["cpt-list", "cpt-list"],
        ["pacman", "pacman -Qq --color never"],
        ["dpkg", "dpkg-query -f '.\\n' -W"],
        ["xbps-query", "xbps-query -l"],
        ["apk", "apk info"],
        ["opkg", "opkg list-installed"],
        ["pacman-g2", "pacman-g2 -Q"],
        ["lvu", "lvu installed"],
        ["tce-status", "tce-status -i"],
        ["pkg_info", "pkg_info"],
        ["pkgin", "pkgin list"],
        ["sorcery", "gaze installed"],
        ["alps", "alps showinstalled"],
        ["butch", "butch list"],
        ["swupd", "swupd bundle-list --quiet"],
        ["pisi", "pisi li"],
        ["pacstall", "pacstall -L"],
        ["rpm", "rpm -qa"],
        ["flatpak", "flatpak list"],
        ["spm", "spm list -i"],
        ["pkg", "pkg info"],

        ["brew", "ls -1A $(brew --cellar)/* $(brew --caskroom)/*"],
        ["emerge", "ls -1A /var/db/pkg/*/*"],
        ["Compile", "ls -1A /Programs/*/"],
        ["eopkg", "ls -1A /var/lib/eopkg/package/*"],
        ["pkgtool", "ls -1A /var/log/packages/*"],
        ["scratch", "ls -1A /var/lib/scratchpkg/index/*/.pkginfo"],
        ["kagami", "ls -1A /var/lib/kagami/pkgs/*"],
    ]

    for pair in pairs:
        try:
            if shutil.which(pair[0]):
                pkgs.append([pair[0], get_lines_count(pair[1])])
        except:
            pass

    report["system"]["pkgs"] = pkgs
    report["system"]["boot_time"] = datetime.datetime.fromtimestamp(
        psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    report["system"]["uptime"] = format_timedelta(
        datetime.datetime.now().timestamp() - psutil.boot_time())

    ###########################
    #                         #
    #     THERMAL SENSORS     #
    #                         #
    ###########################

    report["sensors"] = {}
    report["sensors"]["thermal"] = []

    temps = psutil.sensors_temperatures()
    if temps:
        for name, entries in temps.items():
            obj = {}
            obj["name"] = name
            obj["entries"] = []
            for entry in entries:
                ent_obj = {
                    "name": entry.label or name,
                    "current": entry.current,
                }
                if entry.critical is not None:
                    ent_obj["critical"] = entry.critical

                if entry.high is not None and entry.critical != entry.high:
                    ent_obj["high"] = entry.high

                try:
                    if ent_obj["current"] and ent_obj["high"]:
                        ent_obj["high_percent"] = round(
                            ent_obj["current"] / ent_obj["high"], 2)
                except:
                    pass

                try:
                    if ent_obj["current"] and ent_obj["critical"]:
                        ent_obj["critical_percent"] = round(
                            ent_obj["current"] / ent_obj["critical"], 2)
                except:
                    pass

                obj["entries"].append(ent_obj)

            report["sensors"]["thermal"].append(obj)

    #####################
    #                   #
    #   SOME PROBLEMS   #
    #                   #
    #####################

    try:
        distro = str(get_os_release()[
            "PRETTY_NAME"] or get_os_release()["NAME"]).lower()

        shitty_distro_list = ["manjaro", "zorin", "endeavour", "garuda", "mx linux", "nobara",
                              "antix", "solus", "pop!_os", "artix", "void", "arcolinux", "cachyos"]

        for shit in shitty_distro_list:
            if shit in distro:
                report["problems"].append(
                    {
                        "class": "warning",
                        "id": "warning-shitty-linux-distro",
                        "header": "Shitty Linux distribution",
                        "desc": f"A shitty Linux distribution was detected ({distro}). This operating system is unstable, its behavior is unpredictable and it is not recommended for any kind of usage."
                    }
                )
    except OSError:
        pass

    if not os.path.exists("/run/systemd/system") and platform.system() == "Linux":
        report["problems"].append(
            {
                "class": "warning",
                "id": "warning-legacy-init-system",
                "header": "Legacy init system",
                "desc": "Running Linux, but init system is not systemd. Install systemd to improve system stability, security and convenience."
            }
        )

    for sensor in report["sensors"]["thermal"]:
        for entry in sensor["entries"]:
            if "critical_percent" in entry:
                if entry["critical_percent"] > 0.9:
                    report["problems"].append(
                        {
                            "class": "alert",
                            "id": "alert-overheat",
                            "header": f"{sensor['name']} {entry['name']} critical overheating",
                            "desc": f"Temperature of {sensor['name']} {entry['name']} is {entry['current']}, critical temperature is {entry['critical']} ({entry['critical_percent']*100}%)"
                        }
                    )
                elif entry["critical_percent"] > 0.8:
                    report["problems"].append(
                        {
                            "class": "warning",
                            "id": "warning-overheat",
                            "header": f"{sensor['name']} {entry['name']} severe overheating",
                            "desc": f"Temperature of {sensor['name']} {entry['name']} is {entry['current']}, critical temperature is {entry['critical']} ({entry['critical_percent']*100}%)"
                        }
                    )

    ###################
    #                 #
    #     SYSTEMD     #
    #                 #
    ###################

    try:
        s = json.loads(subprocess.run(['hostnamectl', '--json=pretty'],
                                      stdout=subprocess.PIPE).stdout.decode())
        report["hostname"] = s
    except:
        pass

    if os.path.exists("/run/systemd/system") and platform.system() == "Linux":
        report["systemd"] = {}
        s = subprocess.run(['systemctl', 'list-units', '--state=running', '--plain', '--no-legend', '--no-pager'],
                           stdout=subprocess.PIPE).stdout.decode()

        report["systemd"]["running"] = parse_serives_list(s)

        s = subprocess.run(['systemctl', 'list-units', '--state=exited', '--plain', '--no-legend', '--no-pager'],
                           stdout=subprocess.PIPE).stdout.decode()

        report["systemd"]["exited"] = parse_serives_list(s)

        s = subprocess.run(['systemctl', 'list-units', '--state=failed', '--plain', '--no-legend', '--no-pager'],
                           stdout=subprocess.PIPE).stdout.decode()

        lst = parse_serives_list(s)

        if lst:
            for unit in lst:
                report["problems"].append(
                    {
                        "class": "warning",
                        "id": "warning-systemd-unit-failed",
                        "header": f"{unit['unit']} failed",
                        "desc": f"systemd unit {unit['unit']} has failed."
                    }
                )

        report["systemd"]["failed"] = parse_serives_list(s)
        report["systemd"]["security"] = json.loads(subprocess.run(['systemd-analyze', 'security', '--json=pretty', '--no-pager'],
                                                                  stdout=subprocess.PIPE).stdout.decode())

        for unit in report["systemd"]["security"]:
            if unit['predicate'] == "UNSAFE":
                report["problems"].append(
                    {
                        "class": "notice",
                        "id": "notice-systemd-unit-unsafe",
                        "header": f"{unit['unit']} is unsafe",
                        "desc": f"systemd unit {unit['unit']} is unsafe with exposure {unit['exposure']}/10.0(systemd-analyze security)."
                    }
                )

    cpu = get_cpu_percent_thread.join()
    report["system"]["cpu"]["percent"] = cpu
    if cpu > 0.95:
        report["problems"].append(
            {
                "class": "notice",
                "id": "notice-cpu-overload",
                "header": f"High CPU usage",
                "desc": f"CPU usage is high: {cpu}% (avg {cpu_percent_interval}s)."
            }
        )

    return report


def main():
    BANNER = """                                      __
   _______  ___________ _____  ____ _/ /
  / ___/ / / / ___/ __ `/ __ \/ __ `/ / 
 (__  ) /_/ (__  ) /_/ / / / / /_/ / /  
/____/\__, /____/\__,_/_/ /_/\__,_/_/   
     /____/     
"""

    NAME = "sysanal"
    VERSION = [0, 3, 3]
    NAME_WITH_VERSION = "sysanal " + ".".join([str(x) for x in VERSION])

    if sys.argv.__len__() > 1:
        if sys.argv[1] == "--print":
            report = get_full_report(cpu_percent_interval=1)
            print(json.dumps(report, indent=4))
            exit()


    print(BANNER)
    print(f"Evgeny Vasilievich (https://evgvs.com/) {NAME_WITH_VERSION}")
    print("Running report now...")

    report = get_full_report(cpu_percent_interval=3)

    f = open("report.json", "w+")
    f.write(json.dumps(report, indent=4))
    f.close()
    print("Report written to report.json")


if __name__ == "__main__":
    main()
