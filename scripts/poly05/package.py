
"""Build a private materials ZIP from the named Git commit, retaining byte-identical source tables."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from facts import ROOT, A, C, D, BASE, FREEZE


OLD_RELEASE="https://github.com/Jupiter0914/dip-final-project-lab/releases/tag/poly04-confirm-review-v1"


def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--commit",default="HEAD")
    p.add_argument("--output",type=Path,default=ROOT/"dist/poly05-report-materials.zip")
    a=p.parse_args()
    commit=git("rev-parse",a.commit+"^{commit}").decode().strip()
    tree={path:header.split()[-1] for entry in git("ls-tree","-rz",commit).decode().split("\0") if entry
          for header,path in [entry.split("\t",1)]}
    names={n for n in tree if n.startswith(("report/poly05/","scripts/poly05/","results/poly05/"))}
    names.add("README.md")
    def contents(name):
        return git("cat-file","blob",tree[name])
    for name in list(names):
        if not name.endswith(".md"):continue
        for ref in re.findall(r"\[[^]\n]*\]\(([^) ]+)\)",contents(name).decode()):
            if "://" in ref or ref.startswith("#"):continue
            dest=((ROOT/name).parent/ref.split("#")[0]).resolve().relative_to(ROOT).as_posix()
            names.add(dest)
    fact_sheet=csv.DictReader(io.StringIO(contents("report/poly05/facts.csv").decode("utf-8-sig")))
    names.update(row["original_file"] for row in fact_sheet)
    names.update((A+"leave_one_source.csv",A+"category_sensitivity.csv",A+"cases.csv",A+"cluster.csv",
                  A+"decision.json",C+"checkpoints.csv",C+"rounds.csv",C+"runs.csv",C+"per_run.csv",
                  C+"regions.csv",C+"structural_cost.csv",D+"rounds.csv",
                  "records/poly04/verification.json","records/poly04/journal-check.json",
                  "records/poly04/analysis-protocol.md","records/poly04/freeze-lock.json",
                  "records/attribution.md","records/poly02/research.md"))
    assert names<=tree.keys(),names-tree.keys()
    # One Git reader, with framing by blob size (binary GIF, PNG, SVG and PM31 included).
    ordered=sorted(names)
    stream=subprocess.run(["git","cat-file","--batch"],cwd=ROOT,check=True,
                input="".join(tree[n]+"\n" for n in ordered).encode(),stdout=subprocess.PIPE).stdout
    pos=0; payload={}
    for name in ordered:
        i=stream.index(b"\n",pos)
        oid,kind,size=stream[pos:i].split()
        assert oid.decode()==tree[name] and kind==b"blob"
        end=i+1+int(size);payload[name]=stream[i+1:end]
        assert stream[end:end+1]==b"\n"
        pos=end+1
    assert pos==len(stream)
    info=dict(work_package="POLY05-CLOSEOUT",status="POLY05_REPORT_MATERIALS_READY_PENDING_MAIN_REVIEW",
              commit=commit,base=BASE,science_freeze=FREEZE,scientific_code_changed=False,old_release=OLD_RELEASE,
              original_review_sha256="7dbe8d39e21c33d296e6d747cc253557b7bd3ccd58c9c7d58d7a1f25e4435785",
              entry="report/poly05/manuscript_materials.html",replay="report/poly05/replay/index.html",
              verify="python -B -X utf8 scripts/poly05/verify.py")
    payload["POLY05-INFO.json"]=(json.dumps(info,indent=2)+"\n").encode()
    receipt=io.StringIO(newline="")
    table=csv.writer(receipt,lineterminator="\n");table.writerow(["file","bytes","sha256"])
    for name,b in sorted(payload.items()):
        table.writerow([name,len(b),sha(b)])
    payload["POLY05-SHA256.csv"]=receipt.getvalue().encode()
    a.output.parent.mkdir(exist_ok=True,parents=True)
    if a.output.exists():
        raise FileExistsError(a.output)
    with ZipFile(a.output,"x",compression=ZIP_DEFLATED,compresslevel=8) as archive:
        for name,b in sorted(payload.items()):
            element=ZipInfo(name)
            element.create_system=3; element.external_attr=0o100644<<16
            archive.writestr(element,b,compress_type=ZIP_DEFLATED,compresslevel=8)
    h=sha(a.output.read_bytes())
    a.output.with_suffix(a.output.suffix+".sha256").write_text(h+"  "+a.output.name+"\n",encoding="ascii")
    print(json.dumps(dict(commit=commit,members=len(payload),size=a.output.stat().st_size,sha256=h)))


if __name__=="__main__":
    main()
