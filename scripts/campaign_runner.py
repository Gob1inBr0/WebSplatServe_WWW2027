#!/usr/bin/env python3
"""Remote campaign runner: the whole tt/360 matrix loop lives on the GPU
server. Queue, GPU picking, launch (tmux), completion detection, metrics
harvest and the lightgaussian dependency chain — no local machine involved.

State:  /home/T0ng/campaign/state.json
Results:/home/T0ng/campaign/campaign_results.csv (appended per finished job)
Log:    /home/T0ng/campaign/runner.log
"""
import glob, json, os, subprocess, time

BASE = "/home/T0ng/campaign"
STATE = f"{BASE}/state.json"
CSV = f"{BASE}/campaign_results.csv"
LOG = open(f"{BASE}/runner.log", "a", buffering=1)
RUNS = "/dev/shm/websplatserve/outputs/runs"
DS = "/dev/shm/websplatserve/workspaces/datasets/vanilla-3dgs"

SCENES = ["tt-truck", "tt-train", "360-bicycle", "360-bonsai", "360-counter",
          "360-garden", "360-kitchen", "360-room", "360-stump"]
TRAINABLE = ["vanilla-3dgs", "hac", "hac-plus-plus", "taming3dgs", "megs2", "atomgs",
             "gaussianpro", "scaffold-gs", "eagles", "reduced-3dgs", "contextgs",
             "compgs", "rdo-gaussian", "mini-splatting",
             "gaussian-splatting-lightning", "sog", "octree-gs", "gaussianspa", "fcgs"]
ENVS = {
    "vanilla-3dgs": ("/home/T0ng/algs/gaussian-splatting-main", "/home/T0ng/bin/py-gaussian-splatting-main"),
    "hac": ("/home/T0ng/algs/HAC-main", "/home/T0ng/bin/py-HAC-main"),
    "hac-plus-plus": ("/home/T0ng/HAC-plus-main", "/home/T0ng/bin/python-gpu1"),
    "taming3dgs": ("/home/T0ng/algs/taming-3dgs-main", "/home/T0ng/bin/py-taming-3dgs-main"),
    "megs2": ("/home/T0ng/algs/MEGS-2-main", "/home/T0ng/bin/py-MEGS-2-main"),
    "atomgs": ("/home/T0ng/algs/AtomGS-main", "/home/T0ng/bin/py-AtomGS-main"),
    "gaussianpro": ("/home/T0ng/algs/GaussianPro-version1.0", "/home/T0ng/bin/py-GaussianPro-version1.0"),
    "scaffold-gs": ("/home/T0ng/algs/Scaffold-GS-main", "/home/T0ng/bin/py-Scaffold-GS-main"),
    "eagles": ("/home/T0ng/algs/EAGLES-main", "/home/T0ng/bin/py-EAGLES-main"),
    "reduced-3dgs": ("/home/T0ng/algs/reduced-3dgs-main", "/home/T0ng/bin/py-reduced-3dgs-main"),
    "contextgs": ("/home/T0ng/algs/ContextGS-main", "/home/T0ng/bin/py-ContextGS-main"),
    "compgs": ("/home/T0ng/algs/CompGS-main", "/home/T0ng/bin/py-CompGS-main"),
    "rdo-gaussian": ("/home/T0ng/algs/RDO-Gaussian-main", "/home/T0ng/bin/py-RDO-Gaussian-main"),
    "lightgaussian": ("/home/T0ng/algs/LightGaussian-main", "/home/T0ng/bin/py-LightGaussian-main"),
    "mini-splatting": ("/home/T0ng/algs/Mini-Splatting-main", "/home/T0ng/bin/py-Mini-Splatting-main"),
    "gaussian-splatting-lightning": ("/home/T0ng/algs/gaussian-splatting-lightning-main", "/home/T0ng/bin/py-gaussian-splatting-lightning-main"),
    "sog": ("/home/T0ng/algs/Self-Organizing-Gaussians-main", "/home/T0ng/bin/py-Self-Organizing-Gaussians-main"),
    "octree-gs": ("/home/T0ng/algs/Octree-GS-main", "/home/T0ng/bin/py-Octree-GS-main"),
    "gaussianspa": ("/home/T0ng/algs/GaussianSpa-main", "/home/T0ng/bin/py-GaussianSpa-main"),
    "fcgs": ("/home/T0ng/algs/FCGS-main", "/home/T0ng/bin/py-CompGS-main"),
}
MAX_CONC = 8
MIN_FREE_MB = 8000


def log(msg):
    print(time.strftime("%m-%d %H:%M:%S"), msg, file=LOG, flush=True)


def sh(cmd, timeout=60):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout.strip()


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"done": {}, "inflight": {}, "lg_submitted": {}}


def save(state):
    json.dump(state, open(STATE, "w"), indent=1)


def seed(state):
    """Credit prior successes; mark live platform runs as inflight."""
    for d in glob.glob(f"{RUNS}/*/"):
        name = os.path.basename(d.rstrip("/"))
        ec_path = os.path.join(d, "output", ".wgsc_job", "exit_code")
        ec = None
        if os.path.exists(ec_path):
            try:
                ec = open(ec_path).read().strip()
            except OSError:
                pass
        for scene in SCENES:
            if name.startswith(scene + "-"):
                fam = name[len(scene) + 1:].rsplit("-202610", 1)[0]
                key = f"{scene}|{fam}"
                if ec == "0":
                    if key not in state["done"]:
                        state["done"][key] = {"exit": 0, "dir": d.rstrip("/")}
                elif ec is None and os.path.exists(os.path.join(d, "output", ".wgsc_job")):
                    if key not in state["done"] and key not in state["inflight"]:
                        state["inflight"][key] = {"dir": d.rstrip("/"), "session": "platform"}
    log(f"seed: done={len(state['done'])} inflight={len(state['inflight'])}")


def gpu_free(state=None):
    """Pick the GPU with the most headroom. Reservations subtract ~6 GB per
    in-flight job we launched on that card, because nvidia-smi lags behind
    fresh launches and would otherwise pile every job onto one GPU."""
    out = sh("nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits")
    reserved = {}
    if state:
        for info in state.get("inflight", {}).values():
            g = str(info.get("gpu", ""))
            reserved[g] = reserved.get(g, 0) + 6000
    best, best_free = None, MIN_FREE_MB
    for line in out.splitlines():
        idx, free = [p.strip() for p in line.split(",")]
        free = int(free) - reserved.get(idx, 0)
        if free >= MIN_FREE_MB and free > best_free:
            best, best_free = idx, free
    return best


def launch(scene, family, tag, out_dir, gpu, extra=""):
    repo, py = ENVS[family]
    ds = f"{DS}/{scene}-preview-/workspace"
    script = extra if extra else f"train.py -s {ds} -m {out_dir} --eval --iterations 30000"
    os.makedirs(f"{out_dir}/.wgsc_job", exist_ok=True)
    session = f"camp-{tag}"
    cmd = f"cd {repo} && CUDA_VISIBLE_DEVICES={gpu} {py} {script} ; echo $? > {out_dir}/.wgsc_job/exit_code"
    sh("tmux new-session -d -s " + session + " 'bash -c \"" + cmd + "\"'")
    return session


def harvest(key, out_dir, exit_code):
    scene, family = key.split("|", 1)
    psnr = ssim = lpips = size = ""
    try:
        r = json.load(open(f"{out_dir}/results.json"))
        overall = r.get("ours_30000", r)
        psnr, ssim, lpips = overall.get("PSNR", ""), overall.get("SSIM", ""), overall.get("LPIPS", "")
    except Exception:
        pass
    plys = glob.glob(f"{out_dir}/point_cloud/point_cloud.ply")
    if plys:
        size = os.path.getsize(plys[0])
    with open(CSV, "a") as f:
        f.write(f"{scene},{family},{exit_code},{psnr},{ssim},{lpips},{size},{int(time.time())}\n")


def run_metrics(key, out_dir):
    family = key.split("|", 1)[1]
    repo, py = ENVS.get(family, ("", "python3"))
    try:
        r = subprocess.run(
            ["/bin/bash", "-lc", f"cd {repo} && {py} metrics.py -m {out_dir}"],
            capture_output=True, text=True, timeout=3600)
        log(f"metrics {key}: rc={r.returncode}")
    except Exception as exc:
        log(f"metrics {key} error: {exc}")


def main():
    os.makedirs(BASE, exist_ok=True)
    if not os.path.exists(CSV):
        open(CSV, "w").write("scene,family,exit_code,psnr,ssim,lpips,ply_bytes,ts\n")
    state = load_state()
    seed(state)
    save(state)
    log("runner started")
    while True:
        # 1) reap finished inflight jobs
        for key, info in list(state["inflight"].items()):
            ec_path = os.path.join(info["dir"], ".wgsc_job", "exit_code")
            if os.path.exists(ec_path):
                try:
                    ec = open(ec_path).read().strip()
                except OSError:
                    continue
                if ec == "0" and not os.path.exists(os.path.join(info["dir"], "results.json")):
                    run_metrics(key, info["dir"])
                state["done"][key] = {"exit": ec, "dir": info["dir"]}
                harvest(key, info["dir"], ec)
                if str(info.get("session", "")).startswith("camp-"):
                    sh(f"tmux kill-session -t {info['session']} 2>/dev/null; true")
                del state["inflight"][key]
                log(f"reaped {key}: exit={ec}")
                save(state)
        # 2) fill free slots
        plan = []
        if len(state["inflight"]) < MAX_CONC:
            # priority 1: checkpoint runs (lightgaussian depends on them)
            for scene in SCENES:
                has_ckpt = bool(glob.glob(f"{RUNS}/{scene}-vanilla-ckpt-*/output/chkpnt30000.pth"))
                key = f"{scene}|__ckpt__"
                if not has_ckpt and key not in state["done"] and key not in state["inflight"]:
                    plan.append((scene, "__ckpt__"))
            # priority 2: the plain matrix
            for scene in SCENES:
                for family in TRAINABLE:
                    key = f"{scene}|{family}"
                    if key not in state["done"] and key not in state["inflight"]:
                        plan.append((scene, family))
            # priority 3: lightgaussian once its checkpoint exists
            for scene in SCENES:
                key = f"{scene}|lightgaussian"
                if key in state["done"] or key in state["inflight"] or state["lg_submitted"].get(scene):
                    continue
                if glob.glob(f"{RUNS}/{scene}-vanilla-ckpt-*/output/chkpnt30000.pth"):
                    plan.append((scene, "lightgaussian"))
        for scene, family in plan:
            if len(state["inflight"]) >= MAX_CONC:
                break
            if scene == "360-kitchen":
                if not os.path.exists(f"{DS}/360-kitchen-preview-/workspace/sparse/0/points3D.bin"):
                    continue  # kitchen waits for its COLMAP to finish
            gpu = gpu_free(state)
            if not gpu:
                break
            ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            ds = f"{DS}/{scene}-preview-/workspace"
            if family == "__ckpt__":
                out_dir = f"{RUNS}/{scene}-vanilla-ckpt-{ts}/output"
                session = launch(scene, "vanilla-3dgs", f"{scene}-ckpt", out_dir, gpu,
                                 extra=f"train.py -s {ds} -m {out_dir} --eval --iterations 30000 --checkpoint_iterations 30000")
                state["inflight"][f"{scene}|__ckpt__"] = {"dir": out_dir, "session": session, "gpu": gpu}
                log(f"launched ckpt {scene} on gpu{gpu}")
            elif family == "lightgaussian":
                out_dir = f"{RUNS}/{scene}-lightgaussian-{ts}/output"
                ckpt = glob.glob(f"{RUNS}/{scene}-vanilla-ckpt-*/output/chkpnt30000.pth")[0]
                session = launch(scene, "lightgaussian", f"{scene}-lightgaussian", out_dir, gpu,
                                 extra=f"prune_finetune.py -s {ds} -m {out_dir} --eval --start_checkpoint {ckpt}")
                state["inflight"][key] = {"dir": out_dir, "session": session, "gpu": gpu}
                state["lg_submitted"][scene] = True
                log(f"launched {scene}|lightgaussian on gpu{gpu}")
            else:
                out_dir = f"{RUNS}/{scene}-{family}-{ts}/output"
                session = launch(scene, family, f"{scene}-{family}", out_dir, gpu)
                state["inflight"][f"{scene}|{family}"] = {"dir": out_dir, "session": session, "gpu": gpu}
                log(f"launched {scene}|{family} on gpu{gpu}")
            save(state)
            time.sleep(3)
        time.sleep(60)


if __name__ == "__main__":
    main()
