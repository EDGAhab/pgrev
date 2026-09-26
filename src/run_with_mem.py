#!/usr/bin/env python3
"""Run a command, log output, track wall time and peak RSS of the process tree."""
import subprocess, sys, time, os, threading

def get_tree_rss(pid):
    total = 0
    try:
        # all descendants via pgrep
        out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True)
        pids = [pid] + [int(x) for x in out.stdout.split() if x.strip().isdigit()]
        # walk deeper (children of children)
        seen = set(pids); frontier = list(pids)
        while frontier:
            p = frontier.pop()
            out = subprocess.run(["pgrep", "-P", str(p)], capture_output=True, text=True)
            for x in out.stdout.split():
                if x.strip().isdigit() and int(x) not in seen:
                    seen.add(int(x)); frontier.append(int(x))
        for p in seen:
            try:
                with open(f"/proc/{p}/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            total += int(line.split()[1])  # kB
                            break
            except (FileNotFoundError, ProcessLookupError):
                pass
    except Exception:
        pass
    return total

def main():
    log_path = sys.argv[1]
    cmd = sys.argv[2:]
    t0 = time.time()
    peak = 0
    stop = threading.Event()
    proc_holder = {}
    def sampler():
        while not stop.is_set():
            p = proc_holder.get("p")
            if p is not None:
                rss = get_tree_rss(p.pid)
                nonlocal_peak[0] = max(nonlocal_peak[0], rss)
            time.sleep(1.0)
    nonlocal_peak = [0]
    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    with open(log_path, "w") as log:
        log.write(f"CMD: {' '.join(cmd)}\nSTART: {time.strftime('%F %T')}\n")
        log.flush()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
        proc_holder["p"] = p
        for line in p.stdout:
            log.write(line); log.flush()
        p.wait()
        stop.set(); th.join(timeout=3)
        dt = time.time() - t0
        log.write(f"\nEXIT: {p.returncode}\nWALL_TIME_S: {dt:.1f}\nPEAK_RSS_KB: {nonlocal_peak[0]}\n")
    print(f"EXIT={p.returncode} WALL={dt/60:.1f}min PEAK_RSS_MB={nonlocal_peak[0]/1024:.0f}")

main()
