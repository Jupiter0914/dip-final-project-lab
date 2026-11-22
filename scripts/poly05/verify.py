
"""Read-only closeout checks, including a direct paired reconstruction from original calls."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

import cv2
import numpy as np
from PIL import Image
import evidence
from facts import A, BASE, C, D, FIG, FREEZE, MAT, ROOT, SAMPLES, build, csv_bytes, one, rows, select


def check_close(a,b):
    np.testing.assert_allclose(float(a),float(b),rtol=1e-11,atol=1e-11)


def source_means(pairs):
    values=defaultdict(lambda:defaultdict(list))
    for (id,sess,rep),v in pairs:
        values[id][sess].append(v)
    return {id:np.mean([np.mean(ys,axis=0) for ys in sessions.values()],axis=0)
            for id,sessions in sorted(values.items())}


def bounds(v):
    v=np.array(v,float)
    draws=np.random.default_rng(40121).integers(len(v),size=(10000,len(v)),dtype=np.int32)
    return np.quantile(v[draws].mean(axis=1),[.025,.975])


def independent_stats():
    data=rows(C+"per_run.csv")
    index=defaultdict(dict)
    for r in data:
        key=(r["id"],r["session"],r["rep"])
        group=index[r["dataset"],r["budget"],r["deadline_ms"],r["method"]]
        assert key not in group
        group[key]=r
    checked=0
    receipt={}
    for ds in ("Oxford","LEMS"):
        for budget,t in [(256,100),(256,200),(128,100),(128,200),(512,100),(512,200)]:
            comparisons=[("cross","within_full","R2+")]
            if (budget,t)==(256,100):
                comparisons.extend([("cross","cgal","all"),("cross","cgal_within","all"),("exact","cross","all")])
            for m,b,scope in comparisons:
                left=index[ds,str(budget),str(t),m];right=index[ds,str(budget),str(t),b]
                pairs=[]; coverage=Counter()
                for key in sorted(left):
                    r=left[key];s=right[key]
                    if scope=="R2+" and int(r["rings"])<2:
                        continue
                    ok=(r["status"]=="success",s["status"]=="success")
                    coverage[ok]+=1
                    if all(ok):
                        assert r["actual_bytes"]==s["actual_bytes"]
                        x,y=int(r["xor"]),int(s["xor"])
                        pairs.append((key,(y-x,100*(y-x)/max(1,y),100*(float(r["iou"])-float(s["iou"])),x,y)))
                by=source_means(pairs);v=np.stack(list(by.values()))
                f=dict(dataset=ds,budget=budget,deadline_ms=t,scope=scope,method=m,baseline=b)
                pairing=one(A+"paired_coverage.csv",**f)
                for k,state in [("n_common_runs",(True,True)),("n_neither",(False,False)),("n_method_only",(True,False)),("n_baseline_only",(False,True))]:
                    assert int(pairing[k])==coverage[state]
                assert int(pairing["n_ever_common"])==len(by)
                check_close(v[:,3].mean(),pairing["common_method_xor"])
                check_close(v[:,4].mean(),pairing["common_baseline_xor"])
                for j,k in enumerate(("xor_saved","relative_xor_saved_pct","iou_gain_pp")):
                    summary=one(A+"paired_summary.csv",**f,metric=k)
                    vals=v[:,j];low,high=bounds(vals)
                    for ref,actual in [("mean",vals.mean()),("median",np.median(vals)),("lo",low),("hi",high)]:
                        check_close(summary[ref],actual)
                    assert (int(summary["wins"]),int(summary["ties"]),int(summary["losses"]))==(
                        int((vals>1e-12).sum()), int((abs(vals)<=1e-12).sum()),int((vals< -1e-12).sum()))
                if (m,b,budget,t)==("cross","within_full",256,100):
                    for s in ("S1","S2","S3"):
                        session=[v[0] for v in source_means([p for p in pairs if p[0][1]==s]).values()]
                        published=one(A+"stability.csv",dataset=ds,analysis="session/"+s)
                        check_close(np.mean(session),published["mean"])
                        lo,hi=bounds(session);check_close(lo,published["lo"]);check_close(hi,published["hi"])
                    for name in by:
                        expected=one(A+"leave_one_source.csv",dataset=ds,removed=name)
                        check_close(np.mean([v[0] for id,v in by.items() if id!=name]),expected["mean_without"])
                    receipt[ds]=dict(sources=len(by),matched=len(pairs),mean=v[:,0].mean(),ci=bounds(v[:,0]).tolist())
                checked+=1
    return checked,receipt


def study_population():
    src=select(SAMPLES,dataset="Oxford")
    r0=[r for r in src if int(r["rings"])==0]
    assert [r["id"] for r in r0]==["Egyptian_Mau_20"] and r0[0]["stratum"]=="simple"
    bucket=lambda r:min(int(r["rings"]),2)
    assert Counter(map(bucket,src))=={0:1,1:49,2:150}
    q=select(A+"source_pairs.csv",dataset="Oxford",budget=256,deadline_ms=100,method="cross",baseline="within_full")
    assert Counter(bucket(r) for r in q if int(r["common"]))=={0:1,1:48,2:146}
    timed={}
    for ds in ("Oxford","LEMS"):
        for multi in (False,True):
            ix=[r for r in rows(C+"per_run.csv") if r["budget"]=="256" and r["deadline_ms"]=="100" and r["dataset"]==ds and (not multi or int(r["rings"])>=2)]
            for m in ("cross","within_full"):
                group=[r for r in ix if r["method"]==m]
                timely=sum(r["status"]=="success" for r in group)
                ref=one(A+"coverage.csv",dataset=ds,scope="R2+" if multi else "all",method=m,budget=256,deadline_ms=100)
                assert (timely,len(group))==(int(ref["obs_success"]),int(ref["runs"]))
                timed["/".join([ds,"R2+" if multi else "all",m])]=[timely,len(group)]
    struct=select(C+"structural_cost.csv",dataset="Oxford",budget=256)
    legal=[r for r in struct if r["legal_xor"]!=""]
    recovered=[r for r in legal if r["raw_reason"]!="ok"]
    assert (len(legal),len(recovered))==(197,9)
    summary=one(C+"structure_summary.csv",dataset="Oxford",budget=256)
    for group,col in [(legal,"mean_extra_xor_valid"),(recovered,"mean_extra_xor_recovered")]:
        check_close(np.mean([int(r["legal_xor"])-int(r["unconstrained_xor"]) for r in group]),summary[col])
    clock=select(C+"runs.csv",dataset="Oxford",method="cross",budget=256)
    obs=select(C+"per_run.csv",dataset="Oxford",method="cross",budget=256,deadline_ms=100)
    assert len(clock)==len(obs)==1200
    identity=lambda r:(r["id"],r["session"],r["rep"])
    matches={identity(r):r for r in obs}
    for r in clock:
        check_close(r["end_ms"],(int(r["caller_return_ns"])-int(r["clock_start_ns"]))/1e6)
        for f in ("end_ms","search_end_ms"):
            assert matches[identity(r)][f]==r[f]
    for m in ("within_old","within_full_oldtri","within_full"):
        rounds=select(D+"rounds.csv",method=m)
        s=one(D+"summary-rounds.csv",method=m,condition="fixed2")
        assert len(rounds)==int(s["rounds"])
        for field,k in [("proposed_pairs","proposed"),("accepted","accepted")]:
            assert sum(int(r[field]) for r in rounds)==int(s[k])
        assert sum(int(r["proposed_pairs"])<24 for r in rounds)==int(s["under_24"])
    return timed


def verify_cases():
    joined=json.loads((evidence.REPLAY/"index.json").read_text(encoding="utf-8"))
    page=(evidence.REPLAY/"index.html").read_text(encoding="utf-8")
    assert json.loads(re.search(r'id="saved">(.*?)</script>',page,re.S)[1])==joined
    digests=set()
    for c in joined["cases"]:
        raw,original=evidence.source(one(SAMPLES,dataset=c["dataset"],id=c["id"]),stored_only=True)
        assert "evidence/"+original==c["source_file"]
        assert np.array_equal(np.array(Image.open(evidence.REPLAY/c["raw"])),evidence.paint(raw))
        for m,q in c["methods"].items():
            data=(evidence.REPLAY/q["pm31"]).read_bytes()
            assert hashlib.sha256(data).hexdigest()==q["sha256"]
            shape,rings,parents=evidence.unpack(data)
            assert list(map(len,rings))==q["ring_points"] and q["size"]==len(data) and parents==q["parents"]
            hi=np.zeros((4*shape[0]+5,4*shape[1]+5),np.uint8);restored=np.zeros(shape,bool)
            for ring in rings:
                hi.fill(0)
                cv2.drawContours(hi,[ring],0,255,cv2.FILLED,lineType=cv2.LINE_8)
                restored^=hi[4:4*shape[0]+1:4,4:4*shape[1]+1:4].astype(bool)
            assert np.array_equal(np.array(Image.open(evidence.REPLAY/q["mask"])),evidence.paint(restored))
            assert np.array_equal(np.array(Image.open(evidence.REPLAY/q["errors"])),evidence.paint(raw,restored))
            for k,v in zip(("fp","fn","xor","iou"),evidence.counts(raw,restored)):
                check_close(q[k],v)
            ft=dict(dataset=c["dataset"],id=c["id"],session=c["session"],rep=c["rep"],budget=256,method=m)
            call=one(C+"runs.csv",**ft)
            ev=[r for r in select(C+"checkpoints.csv",**ft) if int(r["received_ns"])-int(call["clock_start_ns"])<=100_000_000][-1]
            assert ev["sha256"]==q["sha256"]
            for field in ("serialized_ms","dispatch_ms","delivered_ms"):
                check_close(q[field],ev[field])
            for field in ("search_end_ms","end_ms"):
                check_close(q[field],call[field])
            if c.get("region"):
                s=c["region"]
                # SAUF labels follow row-major order. Count original, decoded and intersecting pixels anew.
                def labels(mask):
                    pad=np.pad(mask,1).astype(np.uint8)
                    target=pad if s["kind"]=="foreground" else 1-pad
                    return cv2.connectedComponentsWithAlgorithm(target,8 if s["kind"]=="foreground" else 4,cv2.CV_32S,cv2.CCL_SAUF)[1]
                region=labels(raw)==s["reference_id"]; decoded_labels=labels(restored)
                ids=np.unique(decoded_labels[region]);ids=ids[ids!=0]
                assert len(ids)==1
                matched=decoded_labels==ids[0]; key="within" if m=="within_full" else "cross"
                assert region.sum()==s["reference_area"] and matched.sum()==s[key+"_area"]
                check_close((region&matched).sum()/region.sum(),s[key+"_recall"])
            digests.add(q["sha256"])
    a=joined["action"]
    left,bl,_=evidence.decoded(a["before"]["sha256"]);right,al,_=evidence.decoded(a["after"]["sha256"])
    d,r=a["donor"],a["receiver"]
    assert d!=r and np.array_equal(np.delete(bl[d],a["donor_vertex"],0),al[d])
    assert np.array_equal(np.insert(bl[r],a["receiver_edge"]+1,a["insert"],axis=0),al[r])
    assert all(np.array_equal(b,e) for i,(b,e) in enumerate(zip(bl,al)) if i not in (d,r))
    src,_=evidence.source(one(SAMPLES,id=a["id"]),stored_only=True)
    assert [int((src!=x).sum()) for x in (left,right)]==[a[k]["xor"] for k in ("before","after")]
    return len(joined["cases"]),len(digests|{a["before"]["sha256"],a["after"]["sha256"]})


def check_figures_and_links():
    for svg in FIG.glob("*.svg"):
        s=svg.read_text(encoding="utf-8")
        assert "TimesNewRoman" in s and "SimSun" in s and "<text " not in s
        im=Image.open(svg.with_suffix(".png"))
        assert im.width>=2200 and im.info["dpi"][0]>319
    assert len(list(FIG.glob("*.svg")))==6
    texts=list(MAT.glob("*.md"))+[ROOT/"README.md"]
    count=0
    for p in texts:
        for target in re.findall(r"\[[^]\n]*\]\(([^) ]+)\)",p.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            assert (p.parent/unquote(target.split("#")[0])).is_file(),(p,target)
            count+=1
    return count


def git_snapshot():
    def git(*args):
        return subprocess.check_output(["git",*args],cwd=ROOT)
    def listing(ref):
        return dict((path,meta.split()[2]) for row in git("ls-tree","-rz",ref).decode().split("\0") if row
                    for meta,path in [row.split("\t",1)])
    lock=json.loads((ROOT/"records/poly04/freeze-lock.json").read_text())
    slots=[*lock,"records/poly04/freeze-lock.json"]
    base,freeze,now=map(listing,(BASE,FREEZE,"HEAD"))
    assert all(freeze[name]==base[name]==now[name] for name in slots)
    for name,sha in lock.items():
        assert hashlib.sha256((ROOT/name).read_bytes().replace(b"\r\n",b"\n")).hexdigest()==sha
    changed=git("diff","--name-only",BASE,"--").decode().splitlines()
    assert all(x=="README.md" or x.startswith(("report/poly05/","results/poly05/","scripts/poly05/")) for x in changed)
    return len(lock)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--working-fingerprints",type=Path,help="Optional prior SHA-256 list of physical checkout files")
    args=parser.parse_args()
    ledger=build()
    assert csv_bytes(ledger)==(MAT/"facts.csv").read_bytes()
    groups,primary=independent_stats()
    timed=study_population()
    cases,unique=verify_cases()
    links=check_figures_and_links()
    report=dict(facts=len(ledger),raw_comparisons=groups,primary=primary,coverage=timed,
                replay_pairs=cases,distinct_example_files=unique,figures=6,local_markdown_links=links)
    if (ROOT/".git").exists():
        report["unchanged_locked_git_blobs"]=git_snapshot()
    if args.working_fingerprints:
        captured=json.loads(args.working_fingerprints.read_text())
        for name,sha in captured.items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha
        report["unchanged_working_byte_fingerprints"]=len(captured)
    if (ROOT/"POLY05-SHA256.csv").exists():
        for r in rows("POLY05-SHA256.csv"):
            data=(ROOT/r["file"]).read_bytes()
            assert len(data)==int(r["bytes"]) and hashlib.sha256(data).hexdigest()==r["sha256"],r["file"]
        report["hashed_archive_payloads"]=len(rows("POLY05-SHA256.csv"))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
