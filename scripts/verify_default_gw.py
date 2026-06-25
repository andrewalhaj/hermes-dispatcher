import os, time
pid=os.popen("XDG_RUNTIME_DIR=/run/user/0 systemctl --user show -p MainPID --value hermes-gateway.service").read().strip()
active=os.popen("XDG_RUNTIME_DIR=/run/user/0 systemctl --user is-active hermes-gateway.service").read().strip()
env=open("/proc/%s/environ"%pid,"rb").read().decode(errors="replace").split("\x00")
PREFIX="DEEPSEEK_" + "API_KEY="
crit_names=("DEEPSEEK_" + "API_KEY","ANTHROPIC_API_KEY","XAI_API_KEY","DISCORD_BOT_TOKEN","TELEGRAM_BOT_TOKEN")
crit=sorted(set(v.split("=",1)[0] for v in env if v.split("=",1)[0] in crit_names))
ds=[v for v in env if v.startswith(PREFIX)]
tail="<none>"
if ds:
    val=ds[0].split("=",1)[1]; tail=val[len(val)-4:]
lines=[
 "=== default gateway post-restart verification ===",
 "time: %s"%time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
 "PID: %s"%pid,
 "active: %s"%active,
 "critical env vars loaded: %d -> %s"%(len(crit), crit),
 "DEEPSEEK tail: %s (expect 425f = delegation fixed)"%tail,
 "VERDICT: %s"%("PASS - env loaded, delegation key present" if tail=="425f" and active=="active" else "CHECK - investigate"),
]
out="\n".join(lines)
open("/root/.hermes/references/gateway-restart-verify.txt","w").write(out+"\n")
print(out)
