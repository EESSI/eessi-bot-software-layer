#!/usr/bin/env python3
#
# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Samuel Moors (@smoors)
#
# license: GPLv2
#

import argparse
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

RED = "\033[31m"
BLUE = "\033[34m"
GREEN = "\033[32m"
RESET = "\033[0m"

JOB_MANAGER_MODULE = "eessi_bot_job_manager"
EVENT_HANDLER_MODULE = "eessi_bot_event_handler"
DEFAULT_INSTANCE = "eessi-bot"


def parse_args():
    parser = argparse.ArgumentParser(
        usage="%(prog)s {start|stop|restart|status} [options]"
    )
    parser.add_argument("command", choices=("start", "stop", "restart", "status"))
    parser.add_argument(
        "-i", "--instance",
        default=DEFAULT_INSTANCE,
        help=f"bot instance (default: {DEFAULT_INSTANCE})",
    )
    parser.add_argument(
        "-j", "--job-manager-opts",
        default="",
        help="additional job manager options as a string",
    )
    parser.add_argument(
        "-e", "--event-handler-opts",
        default="",
        help="additional event handler options as a string",
    )
    return parser.parse_args()


def get_cmdline(pid):
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return []
    return [arg.decode(errors="replace") for arg in data.split(b"\0") if arg]


def find_processes(module, instance):
    processes = []

    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue

        pid = int(proc.name)
        if pid == os.getpid():
            continue

        cmdline = get_cmdline(pid)
        if not cmdline:
            continue

        try:
            module_index = cmdline.index("-m")
        except ValueError:
            continue

        if module_index + 1 >= len(cmdline) or cmdline[module_index + 1] != module:
            continue

        for i, arg in enumerate(cmdline[:-1]):
            if arg == "--instance" and cmdline[i + 1] == instance:
                processes.append(pid)
                break

    return processes


def start_process(module, instance, opts):
    cmd = ["python3", "-m", module, "--instance", instance]
    if opts:
        cmd.extend(shlex.split(opts))

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    subprocess.Popen(cmd, env=env, start_new_session=True)


def start_bot(instance, job_manager_opts, event_handler_opts):
    if find_processes(JOB_MANAGER_MODULE, instance):
        print(f"{BLUE}>>> job manager for bot instance '{instance}' is already running{RESET}")
    else:
        print(f"{BLUE}>>> starting job manager for bot instance '{instance}'...{RESET}")
        start_process(JOB_MANAGER_MODULE, instance, job_manager_opts)

    if find_processes(EVENT_HANDLER_MODULE, instance):
        print(f"{GREEN}>>> event handler for bot instance '{instance}' is already running{RESET}")
    else:
        print(f"{GREEN}>>> starting event handler for bot instance '{instance}'...{RESET}")
        start_process(EVENT_HANDLER_MODULE, instance, event_handler_opts)


def stop_processes(module, instance):
    for pid in find_processes(module, instance):
        try:
            cmdline = get_cmdline(pid)
            os.kill(pid, signal.SIGTERM)
            print(f"killed (pid {pid}): {shlex.join(cmdline)}")
        except ProcessLookupError:
            pass


def stop_bot(instance):
    if find_processes(EVENT_HANDLER_MODULE, instance):
        print(f"{RED}>>> stopping event handler for bot instance '{instance}'...{RESET}")
        stop_processes(EVENT_HANDLER_MODULE, instance)
    else:
        print(f"{RED}>>> event handler for bot instance '{instance}' is not running{RESET}")

    if find_processes(JOB_MANAGER_MODULE, instance):
        print(f"{RED}>>> stopping job manager for bot instance '{instance}'...{RESET}")
        stop_processes(JOB_MANAGER_MODULE, instance)
    else:
        print(f"{RED}>>> job manager for bot instance '{instance}' is not running{RESET}")


def status_bot(instance):
    if find_processes(JOB_MANAGER_MODULE, instance):
        print(f"{BLUE}>>> job manager for bot instance '{instance}' is running{RESET}")
    else:
        print(f"{RED}>>> job manager for bot instance '{instance}' is not running{RESET}")

    if find_processes(EVENT_HANDLER_MODULE, instance):
        print(f"{GREEN}>>> event handler for bot instance '{instance}' is running{RESET}")
    else:
        print(f"{RED}>>> event handler for bot instance '{instance}' is not running{RESET}")


def main():
    args = parse_args()

    if args.command == "start":
        start_bot(args.instance, args.job_manager_opts, args.event_handler_opts)
        time.sleep(2)
        status_bot(args.instance)
    elif args.command == "stop":
        stop_bot(args.instance)
    elif args.command == "restart":
        stop_bot(args.instance)
        time.sleep(1)
        start_bot(args.instance, args.job_manager_opts, args.event_handler_opts)
        time.sleep(2)
        status_bot(args.instance)
    elif args.command == "status":
        status_bot(args.instance)


if __name__ == "__main__":
    main()
