"""Download the identified public original resources and verify their exact bytes."""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path
from .data import DATA,REC,sha

SOURCES={
 "upf.zip":("https://addons.mathworks.com/downloads/9b/9bf0e77b-720e-422d-a51d-beee4b9483fe/1.0.0/unconstrained_polygonal_fitting-1.0.0.zip","67c9a9f527142f8e2e5f4cec7a8a2724930059ecb876cc678095dbc3a868c1bc"),
 "shapes-author.bin":("https://drive.usercontent.google.com/download?id=1_A3u9nnwx--FMbmn8HAjBdRvkYtL4j4W&export=download&confirm=t","f6a132c16ca4800fc9cfbe3d469a086599aba67783448362c0bc2275bf7e6d1c"),
 "paper.pdf":("https://mdpi-res.com/d_attachment/algorithms/algorithms-17-00025/article_deploy/algorithms-17-00025-v2.pdf","b61b404a1cf4dff210c5832fa806506f53e432009425e21e2d0969709531a31a")}


def main():
    DATA.mkdir(parents=True,exist_ok=True)
    report={}
    for name,(url,digest) in SOURCES.items():
        path=DATA/name
        if not path.exists():
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=60) as src:
                raw=src.read()
            if sha(raw)!=digest: raise ValueError(f"Different download: {name}")
            path.write_bytes(raw)
        if sha(path.read_bytes())!=digest: raise ValueError(name)
        report[name]=dict(url=url,bytes=path.stat().st_size,sha256=digest)
    with zipfile.ZipFile(DATA/"upf.zip") as archive:
        dest=DATA/"upf"
        if archive.testzip() or not all((dest/n).resolve().is_relative_to(dest.resolve()) for n in archive.namelist()):
            raise ValueError("Invalid author ZIP")
        archive.extractall(dest)
        report["source_members"]={n:sha(archive.read(n)) for n in archive.namelist()}
    REC.mkdir(parents=True,exist_ok=True)
    (REC/"resources.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("Author code, PDF and RAR verified")


if __name__=="__main__":
    main()
