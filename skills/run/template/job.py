"""Kaggle job template: parallel workers (one per GPU, or one per CPU core on CPU sessions),
outputs in /kaggle/working, optional cloudflared tunnel. Fill in SETUP, TASKS and process().
The job always ends by itself: after the work, and after at most SERVE_SECONDS of serving."""
import glob, json, os, re, shutil, subprocess, sys, threading, traceback, urllib.request
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import multiprocessing as mp

# Keep heavy imports (torch, etc.) inside process(): a top-level import runs before
# worker() sets OMP_NUM_THREADS and defeats the one-thread-per-CPU-worker setting.

OUT = "/kaggle/working"
SERVE_SECONDS = 0       # >0: expose OUT through a cloudflared quick tunnel for at most this long after finishing
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
    with open(f"{OUT}/items-{slot}.jsonl", "a") as log:  # written per item, so a crash keeps finished work
        for it in items:
            try:
                r = {"ok": True, **process(it, device)}
            except Exception:
                r = {"ok": False, "item": it, "error": traceback.format_exc()}
            log.write(json.dumps(r) + "\n"); log.flush()
            print(f"PROGRESS worker={slot} item={it}", flush=True)


def gpu_count():
    try:
        return subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.count("GPU ")
    except FileNotFoundError:
        return 0


def serve(stop):
    """Serve OUT on :8000; GET /__shutdown sets `stop` so the agent can end the job early."""
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/__shutdown":
                self.send_response(200); self.end_headers(); self.wfile.write(b"bye\n"); stop.set()
            else:
                super().do_GET()
        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 8000), partial(Handler, directory=OUT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def tunnel():
    subprocess.run("wget -q -O /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /tmp/cloudflared", shell=True, check=True)
    cf = subprocess.Popen(["/tmp/cloudflared", "tunnel", "--no-autoupdate", "--url", "http://localhost:8000"], stderr=subprocess.PIPE, text=True)
    for line in cf.stderr:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            # keep draining cloudflared's log, or the pipe fills up and the tunnel stalls
            threading.Thread(target=lambda: [None for _ in cf.stderr], daemon=True).start()
            print("TUNNEL_URL:", m.group(0), flush=True)
            return m.group(0)


def main():
    gpus = gpu_count()
    ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    print(f"RESOURCES: cpus={os.cpu_count()} ram_gb={ram:.1f} disk_free_gb={shutil.disk_usage(OUT).free / 2**30:.0f} gpus={gpus}", flush=True)
    print("INPUT:", sorted(glob.glob("/kaggle/input/**", recursive=True))[:50], flush=True)
    try:
        urllib.request.urlopen("https://pypi.org", timeout=10); net = True
    except Exception:
        net = False
    print("INTERNET:", net, flush=True)
    if SETUP:
        subprocess.run(SETUP, shell=True, check=True)
    stop = threading.Event()
    url = None
    if SERVE_SECONDS and net:
        serve(stop); url = tunnel()

    n = gpus or os.cpu_count()
    chunks = [TASKS[i::n] for i in range(n)]
    crash = None
    try:
        # spawn is required for CUDA in subprocesses, and it requires the __main__ guard below.
        with ProcessPoolExecutor(n, mp_context=mp.get_context("spawn")) as ex:
            list(ex.map(worker, range(n), chunks))
    except Exception as e:  # e.g. BrokenProcessPool after an OOM kill: keep what the workers already wrote
        crash = repr(e); print("CRASH:", crash, flush=True)

    results = [json.loads(l) for f in sorted(glob.glob(f"{OUT}/items-*.jsonl")) for l in open(f)]
    summary = {"workers": n, "gpus": gpus, "internet": net, "tunnel": url, "crash": crash,
               "ok": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results),
               "missing": len(TASKS) - len(results)}
    json.dump({"summary": summary, "results": results}, open(f"{OUT}/result.json", "w"), indent=2)
    print("RESULT:", json.dumps(summary), flush=True)
    if url:
        print(f"SERVING up to {SERVE_SECONDS}s (GET {url}/__shutdown to stop now)", flush=True)
        stop.wait(SERVE_SECONDS)
    print("DONE", flush=True)


if __name__ == "__main__":  # mandatory: without it every spawned worker re-runs the script (BrokenProcessPool)
    main()
