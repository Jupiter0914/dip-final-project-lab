"""Build an immutable private review bundle, or recompute the paired evidence offline."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from collections import defaultdict
import numpy as np
from poly03.full_verify import parse,paint,expected_tree
from poly02.data import rows,sha
from .study import ROOT,REC,WORK,RESULTS,config,manifest,load_input
from .freeze import verify


def checked_supplements(stage):
    folder=RESULTS/stage
    source={(r["dataset"],r["id"]):r for r in manifest(config(stage))}
    counter=0
    with zipfile.ZipFile(WORK/stage/"structure_attempts.zip") as z:
        assert z.testzip() is None
        ids=set()
        for r in rows(folder/"structural_cost.csv"):
            raw,_=load_input(source[r["dataset"],r["id"]],stage)
            for key,name in [("raw_allocation_sha256","unconstrained_xor"),("legal_seed_sha256","legal_xor")]:
                digest=r.get(key)
                if not digest:continue
                blob=z.read(digest+".pm3");ids.add(digest)
                assert sha(blob)==digest and len(blob)<=int(r["budget"])
                shape,rings,parents=parse(blob)
                assert raw.shape==shape
                if key=="legal_seed_sha256":assert expected_tree(rings,parents)
                pred=np.zeros(shape,np.uint8)
                for p in rings:pred^=paint(shape,p)
                assert int(np.count_nonzero(raw!=pred))==int(r[name])
                counter+=1
            if r.get("validity_cost_xor"):
                assert int(r["validity_cost_xor"])==int(r["legal_xor"])-int(r["unconstrained_xor"])
        assert {f+".pm3" for f in ids}==set(z.namelist())
    from .engine_audit import audit_screen
    checked=valid_skips=0
    disagreements=json.loads((folder/"exact_disagreements.json").read_text(encoding="utf-8"))
    failures={(r["dataset"],r["id"],r["sha256"]):r for r in disagreements}
    with zipfile.ZipFile(WORK/stage/"outputs.zip") as z:
        prev=None
        for r in rows(folder/"exact_screen.csv"):
            pair=(r["dataset"],r["id"])
            if pair!=prev: raw,_=load_input(source[pair],stage);prev=pair
            b=z.read(r["sha256"]+".pm3")
            report=audit_screen(raw,256,b)
            for k in ("before_xor","before_add","proposed_pairs","xor_improving","skipped_by_add","valid_skipped_by_add"):
                assert int(r[k])==report[k],(pair,k)
            assert (r["choices_differ"]=="True")==report["choices_differ"]
            if report["choices_differ"] or report["valid_skipped_by_add"]:
                logged=failures.pop((*pair,r["sha256"]))
                assert json.loads(json.dumps(report["candidates"]))==logged["candidates"]
            checked+=1;valid_skips+=report["valid_skipped_by_add"]
    assert not failures
    return dict(seed_attempts_scored=counter,diagnostic_checkpoint_states=checked,valid_additive_filter_misses=valid_skips)


def fixed_ablation():
    from poly02.verify import IndependentScore
    sources={(r["dataset"],r["id"]):r for r in manifest(config("dev"))}
    folder=RESULTS/"dev_fixed"
    entries=rows(folder/"per_image.csv")
    calls=0;scored=0
    with zipfile.ZipFile(folder/"evidence.zip") as z:
        assert z.testzip() is None
        journal=[json.loads(x) for x in z.read("calls.jsonl").decode("utf-8").splitlines()]
        assert len(journal)==len(entries)
        for r,j in zip(entries,journal):
            assert (r["dataset"],r["id"],r["method"])==(j["dataset"],j["id"],j["method"])
            result=j["result"];events=j["events"]
            assert result["status"]==r["status"] and result["rounds"]<=2
            for a in result["round_log"]:
                assert 0<=a["proposed_pairs"]<=24
            if events:
                raw,_=load_input(sources[r["dataset"],r["id"]],"dev")
                score=IndependentScore(raw)
                for event in (events[0],events[-1]):
                    blob=z.read("polygons/"+event["sha256"]+".pm3")
                    assert sha(blob)==event["sha256"]
                    shape,polys,parent=parse(blob);pred=np.zeros(shape,np.uint8)
                    for p in polys:pred^=paint(shape,p)
                    q=score.measure(pred)
                    if event is events[0]:assert q["xor"]==int(r["initial_xor"])
                    if event is events[-1]:assert all(abs(float(r[k])-v)<1e-12 for k,v in q.items())
                scored+=1
            calls+=1
    return dict(calls=calls,valid=scored)


def reencode_examples(stage):
    from .engine import encode
    folder=RESULTS/stage
    named={(r["dataset"],r["id"]):r for r in manifest(config(stage))}
    examples=rows(folder/"analysis/cases.csv")
    table={(r["dataset"],r["id"],r["session"],r["rep"],r["method"],r["budget"],r["deadline_ms"]):r
           for r in rows(folder/"per_run.csv")}
    done=set()
    for case in examples:
        for method in ("cross","within_full"):
            key=(case["dataset"],case["id"],case["session"],case["rep"],method,"256","100")
            if key in done:continue
            r=table[key];assert r["status"]=="success"
            raw,_=load_input(named[key[:2]],stage)
            seen=[]
            result=encode(raw,256,method,lambda b,e:seen.append(b),max_ms=float("inf"),max_rounds=int(r["round"]))
            assert result["status"]=="success" and sha(seen[-1])==r["sha256"]
            done.add(key)
    return len(done)


def audit():
    # Build-integrity and decoded-science checks have different scopes.
    integrity=ROOT/"POLY04-SHA256.csv"
    if integrity.exists():
        for r in rows(integrity):
            path=ROOT/r["path"]
            with path.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
            assert path.stat().st_size==int(r["bytes"]) and digest==r["sha256"],r["path"]
    verify(offline=True)
    data=json.loads(subprocess.check_output([sys.executable,"-X","utf8","-m","poly04.data_audit"],cwd=ROOT,text=True,encoding="utf-8"))
    assert data==json.loads((REC/"data-audit.json").read_text(encoding="utf-8"))
    from .analysis import verify_analysis
    from .pixels import check_stage
    from .replay_journals import audit as audit_journals
    result={"inputs":data["materialized_native_inputs"],"known_source_intersections":data["known_intersections"],
            "known_two_rounds":fixed_ablation()}
    for stage in ("dev","confirm"):
        print("Audit",stage,"timing and native files",flush=True)
        j=audit_journals(stage)
        print("Audit",stage,"independent region and boundary scores",flush=True)
        p=check_stage(stage)
        s=checked_supplements(stage)
        a=verify_analysis(RESULTS/stage,stage,config(stage))
        result[stage]=dict(journals=j,pixels=p,supplement=s,statistics=a,source_reencodings=reencode_examples(stage))
    published=REC/"verification.json"
    if published.exists():
        assert result==json.loads(published.read_text(encoding="utf-8-sig"))
    print("AUDIT_JSON "+json.dumps(result,ensure_ascii=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),flush=True)
    return result


def pack():
    git=lambda *args:subprocess.check_output(["git",*args],cwd=ROOT)
    if git("status","--porcelain","--untracked-files=all").strip():
        raise ValueError("Build from the clean fixed review commit")
    commit=git("rev-parse","HEAD").decode().strip()
    freeze=git("rev-parse","poly04-confirm-freeze-v1").decode().strip()
    sampling=git("rev-parse","poly04-sampling-v1").decode().strip()
    target=ROOT/"dist/poly04-confirm-review.zip"
    target.parent.mkdir(exist_ok=True)
    recorded={}
    def add(archive,name,data):
        digest=sha(data)
        if name in recorded:
            if recorded[name]["sha256"]!=digest:raise ValueError(name)
            return
        zi=zipfile.ZipInfo(name,(2020,1,1,0,0,0))
        archive.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
        recorded[name]=dict(path=name,bytes=len(data),sha256=digest)
    with zipfile.ZipFile(target,"w") as out:
        with zipfile.ZipFile(io.BytesIO(git("archive","--format=zip",commit))) as snapshot:
            for name in sorted(snapshot.namelist()):
                if not name.endswith("/"):add(out,name,snapshot.read(name))
        for stage in ("dev","confirm"):
            for r in manifest(config(stage)):
                name=r["file"];raw=(ROOT/name).read_bytes()
                assert sha(raw)==(r.get("raw_sha256") or r.get("sha256"))
                add(out,name,raw)
            for f in ("outputs.zip","journals.zip","structure_attempts.zip"):
                name=f"local/poly04/{stage}/{f}"
                add(out,name,(ROOT/name).read_bytes())
            # Large plain CSVs, when retained outside Git, remain first-class archive members.
            for path in sorted((RESULTS/stage).rglob("*")):
                if path.is_file() and path.relative_to(ROOT).as_posix() not in recorded:
                    add(out,path.relative_to(ROOT).as_posix(),path.read_bytes())
        add(out,"POLY04-INFO.json",json.dumps(dict(commit=commit,sampling=sampling,scientific_freeze=freeze,
            offline="python -X utf8 -m poly04.review audit"),indent=2).encode())
        f=io.StringIO(newline="")
        w=csv.DictWriter(f,fieldnames=["path","bytes","sha256"],lineterminator="\n");w.writeheader()
        w.writerows(recorded.values())
        out.writestr(zipfile.ZipInfo("POLY04-SHA256.csv",(2020,1,1,0,0,0)),f.getvalue().encode(),
                     compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
    with target.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
    target.with_name(target.name+".sha256").write_text(digest+"  "+target.name+"\n",encoding="ascii")
    print(json.dumps(dict(commit=commit,freeze=freeze,sampling=sampling,bytes=target.stat().st_size,sha256=digest,members=len(recorded)+1)))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["build","audit"])
    if p.parse_args().action=="build":pack()
    else:audit()
