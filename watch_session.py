"""
watch_session.py — Poll a session until a BRAIN simulation PASSES.
Usage: python3 watch_session.py <session_id>
"""
import sys, time, httpx

SID = sys.argv[1] if len(sys.argv) > 1 else None
if not SID:
    print("Usage: python3 watch_session.py <session_id>")
    sys.exit(1)

BASE = "http://localhost:8000"

print(f"▶ OpenAlpha - Quant  |  Session: {SID}")
print("━" * 55)
print("Running until a BRAIN simulation PASSES...")
print()

start = time.time()
tick  = 0

while True:
    time.sleep(10)
    tick += 1
    elapsed = int(time.time() - start)

    try:
        d = httpx.get(f"{BASE}/session/{SID}", timeout=10).json()
    except Exception as e:
        print(f"  t={elapsed}s | poll error: {e}")
        continue

    status  = d.get("status", "?")
    cycle   = d.get("cycle", 0)
    alphas  = d.get("passed_alphas", [])
    err_msg = d.get("error_message", "")

    brain_parts = []
    brain_pass  = None

    for a in alphas:
        br = a.get("brain") or {}
        bs = br.get("status", "PENDING")
        if bs not in ("PENDING", None):
            rs = br.get("real_sharpe", "?")
            rf = br.get("real_fitness", "?")
            rt = br.get("real_turnover", "?")
            part = f"[{a['alpha_id']}] BRAIN={bs} S={rs} F={rf} TO={rt}%"
            if br.get("error_message"):
                part += f" | {br['error_message'][:45]}"
            brain_parts.append(part)
            if bs == "PASS":
                brain_pass = a

    line = f"t={elapsed}s | {status:14} cyc={cycle} pass={len(alphas)}"
    if brain_parts:
        line += "  |  " + "  ".join(brain_parts)
    if err_msg:
        line += f"  SYS_ERR:{err_msg[:40]}"
    print(line)

    if brain_pass:
        br = brain_pass.get("brain") or {}
        print()
        print("━" * 55)
        print("  ╔══════════════════════════════════════════════╗")
        print("  ║   ALPHA SUBMITTED TO WORLDQUANT BRAIN  ✓    ║")
        print("  ╚══════════════════════════════════════════════╝")
        print(f"  Alpha ID (local) : {brain_pass['alpha_id']}")
        print(f"  BRAIN alpha ID   : {br.get('alpha_id', 'n/a')}")
        print(f"  Expression       : {brain_pass['expression'][:85]}")
        print(f"  Dataset          : {brain_pass['fingerprint']['dataset']}")
        print(f"  Topology         : {brain_pass.get('ast_topology','n/a')}")
        print()
        print("  ── REAL BRAIN METRICS ──────────────────────────")
        print(f"  Sharpe           : {br.get('real_sharpe')}")
        print(f"  Fitness          : {br.get('real_fitness')}")
        print(f"  Turnover         : {br.get('real_turnover')}%")
        print(f"  Returns          : {br.get('real_returns')}")
        print(f"  Gate failures    : {br.get('gate_failures') or 'NONE — ALL GATES PASSED ✓'}")
        sys.exit(0)

    if status == "ERROR" and not any(
        (a.get("brain") or {}).get("status") == "PENDING" for a in alphas
    ):
        print(f"\n⚠  Session entered ERROR state: {err_msg[:120]}")
        sys.exit(1)
