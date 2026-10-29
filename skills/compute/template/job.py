"""Kaggle job template: parallel workers (one per GPU, or one per CPU core on CPU sessions),
outputs in /kaggle/working, optional cloudflared tunnel. Fill in SETUP, TASKS and process()."""
import json, os, re, shutil, subprocess, sys, time, traceback, urllib.request
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp

OUT = "/kaggle/working"
SERVE_SECONDS = 0       # >0: expose OUT through a cloudflared quick tunnel and keep it up this long after finishing
SETUP = ""              # e.g. "pip install -q faster-whisper" (needs internet)
TASKS = list(range(8))  # work items; each worker gets an interleaved slice


def process(item, device):
    """Process ONE item on `device` ("cuda:N" or "cpu"). Return something JSON-serializable."""
    import torch
    a = torch.randn(2048, 2048, device=device)
    return {"item": item, "sum": float((a @ a).sum())}


def worker(slot, items):
    device = f"cuda:{slot}" if gpu_count() else "cpu"
    if device == "cpu":
        os.environ["OMP_NUM_THREADS"] = "1"  # one process per core; avoid thread oversubscription
    out = []
    for it in items:
        try:
            out.append({"ok": True, **process(it, device)})
        except Exception:
            out.append({"ok": False, "item": it, "error": traceback.format_exc()})
        print(f"PROGRESS worker={slot} item={it}", flush=True)
    return out


def gpu_count():
    try:
        return subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.count("GPU ")
    except FileNotFoundError:
        return 0


def tunnel():
    subprocess.run("wget -q -O /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared", shell=True, check=True)
    subprocess.Popen([sys.executable, "-m", "http.server", "8000", "-d", OUT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cf = subprocess.Popen(["/tmp/cloudflared", "tunnel", "--no-autoupdate", "--url", "http://localhost:8000"], stderr=subprocess.PIPE, text=True)
    for line in cf.stderr:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            print("TUNNEL_URL:", m.group(0), flush=True)
            return m.group(0)


def main():
    gpus = gpu_count()
    ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    print(f"RESOURCES: cpus={os.cpu_count()} ram_gb={ram:.1f} disk_free_gb={shutil.disk_usage(OUT).free / 2**30:.0f} gpus={gpus}", flush=True)
    try:
        urllib.request.urlopen("https://pypi.org", timeout=10); net = True
    except Exception:
        net = False
    print("INTERNET:", net, flush=True)
    if SETUP:
        subprocess.run(SETUP, shell=True, check=True)
    url = tunnel() if SERVE_SECONDS and net else None

    n = gpus or os.cpu_count()
    chunks = [TASKS[i::n] for i in range(n)]
    # spawn is required for CUDA in subprocesses, and it requires the __main__ guard below.
    with ProcessPoolExecutor(n, mp_context=mp.get_context("spawn")) as ex:
        results = [r for part in ex.map(worker, range(n), chunks) for r in part]

    summary = {"workers": n, "gpus": gpus, "internet": net, "tunnel": url,
               "ok": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results)}
    json.dump({"summary": summary, "results": results}, open(f"{OUT}/result.json", "w"), indent=2)
    print("RESULT:", json.dumps(summary), flush=True)
    if url:
        print(f"SERVING {SERVE_SECONDS}s", flush=True); time.sleep(SERVE_SECONDS)
    print("DONE", flush=True)


if __name__ == "__main__":  # mandatory: without it every spawned worker re-runs the script (BrokenProcessPool)
    main()
