"""Measure CGAL 5.4 address-ordered constraints, seed controls and exact-cost coordinate ties."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from itertools import combinations
from pathlib import Path
import numpy as np
from .cgal_build import ROOT,FILENAME,SHA256,kernel_command,linux_path
from .cgal_recheck import prepare,quality
from .maskcodec import length

LOCAL=ROOT/"local/poly03/cgal_variation"
OUT=ROOT/"results/poly03/cgal_variation"
EXE=LOCAL/"diagnostic-worker"

BUILD=r'''
import hashlib,sys,pathlib,subprocess,tempfile
archive,source,destination=sys.argv[1:]
with tempfile.TemporaryDirectory(prefix="poly03-cgal-diagnostic-") as tmp:
    subprocess.run(["dpkg-deb","-x",archive,tmp],check=True)
    include=pathlib.Path(tmp)/"usr/include"
    header=include/"CGAL/Polyline_simplification_2/simplify.h"
    original=header.read_bytes()
    assert hashlib.sha256(original).hexdigest()=='15b5227967929fcebb31dfb39da0adbca6e78b49e6baa25c725da006c62c4661'
    text=original.decode("utf-8")
    for a,b in [("(*x)","(*y)"),("x","y")]:
        key=f"return {a}->cost() < {b}->cost();"
        replacement=(f"if (!::poly03_xy_ties || {a}->cost() != {b}->cost()) "+key+
            f"\n      return CGAL::compare_xy({a}->point(), {b}->point()) == CGAL::SMALLER;")
        if text.count(key)!=1: raise ValueError(key)
        text=text.replace(key,replacement)
    header.write_text("extern bool poly03_xy_ties;\n"+text)
    subprocess.run(["g++","-O2","-std=c++17","-DNDEBUG","-frounding-math","-I"+str(include),source,
                    "-lgmp","-lmpfr","-o",destination],check=True)
    print("original_simplify_header_sha256",hashlib.sha256(original).hexdigest())
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=LOCAL/"rerun-trace")
    parser.add_argument("--no-build",action="store_true")
    args=parser.parse_args()
    directory=args.output
    directory.mkdir(parents=True,exist_ok=False)
    LOCAL.mkdir(parents=True,exist_ok=True)
    arc=ROOT/"data/poly03/cgal"/FILENAME
    assert hashlib.sha256(arc.read_bytes()).hexdigest()==SHA256
    if not args.no_build or not EXE.exists():
        compiled=subprocess.run(kernel_command("python3","-",linux_path(arc),linux_path(Path(__file__).with_suffix(".cpp")),
                                              linux_path(EXE)),input=BUILD.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        if compiled.returncode:
            raise RuntimeError(compiled.stderr.decode(errors="replace"))
        print(compiled.stdout.decode().strip(),flush=True)
    name="scottish_terrier_199"
    raw,rings,parents=prepare(name)
    target=(128-length(parents,0))//4
    request=[f"{len(rings)} {target}"]
    for ring in rings:
        request.append(str(len(ring)))
        request.extend(f"{int(x)} {int(y)}" for x,y in ring)
    payload=("\n".join(request)+"\n").encode()
    input_hash=hashlib.sha256(payload).hexdigest()
    trials=[]
    traces=[]
    for cost in ("squared","scaled"):
        for policy in ("upstream","xy"):
            for seed in (None,7,47):
                # Two process launches and five consecutive identical inputs per launch.
                for process in range(2):
                    cmd=kernel_command(linux_path(EXE),cost,str(-1 if seed is None else seed),"5",policy)
                    result=subprocess.run(cmd,input=payload,capture_output=True,check=True)
                    for idx,line in enumerate(result.stdout.splitlines()):
                        r=json.loads(line)
                        out=[np.asarray(v,np.int32) for v in r["rings"]]
                        q=quality(raw,out,parents)
                        h=hashlib.sha256(json.dumps(r["events"],separators=(",",":")).encode()).hexdigest()
                        tr=dict(id=name,budget=128,target=target,input_sha256=input_hash,policy=policy,seed="default" if seed is None else seed,
                                process=process,repeat=idx,cost=cost,ring_order=",".join(map(str,r["ring_order"])),
                                trace_sha256=h,pops=len(r["events"]),**q)
                        trials.append(tr)
                        traces.append(r["events"])
    def counts(group):return (len({r["ring_order"] for r in group}),len({r["trace_sha256"] for r in group}),len({r["digest"] for r in group}))
    summary=[]
    for c in ("squared","scaled"):
        for p in ("upstream","xy"):
            for s in ("default",7,47,"all"):
                g=[r for r in trials if r["cost"]==c and r["policy"]==p and (s=="all" or r["seed"]==s)]
                a,b,d=counts(g)
                summary.append(dict(cost=c,policy=p,seed=s,n=len(g),ring_orders=a,pop_traces=b,output_files=d,
                                    min_xor=min(r["xor"] for r in g),max_xor=max(r["xor"] for r in g),
                                    digital_success=sum(r["digital"]=="ok" for r in g)))
    witnesses=[]
    for c in ("squared","scaled"):
        indices=[i for i,r in enumerate(trials) if r["policy"]=="upstream" and r["seed"]==7 and r["cost"]==c]
        options=[(i,j) for i,j in combinations(indices,2) if trials[i]["ring_order"]!=trials[j]["ring_order"] and trials[i]["digest"]!=trials[j]["digest"]]
        if options:
            i,j=options[0]
            step=next(n for n,(a,b) in enumerate(zip(traces[i],traces[j])) if a!=b)
            witnesses.append(dict(cost=c,first_divergent_pop_index=step,left=trials[i],right=trials[j],
                left_xy_cost_current_vertices=traces[i][step],right_xy_cost_current_vertices=traces[j][step],
                same_numeric_cost=traces[i][step][2]==traces[j][step][2],
                same_vertex_count=traces[i][step][3]==traces[j][step][3]))
    for data,fn in [(trials,"trace-runs.csv"),(summary,"seed-and-tie-summary.csv")]:
        with (directory/fn).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator="\n");w.writeheader();w.writerows(data)
    (directory/"first-divergence.json").write_text(json.dumps(witnesses,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    print(json.dumps(witnesses))


if __name__=="__main__":main()
