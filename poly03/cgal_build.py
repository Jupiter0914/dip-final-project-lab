"""Fetch locked Ubuntu CGAL headers and build using native Linux or the existing WSL distro."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FILENAME = "libcgal-dev_5.4-1_amd64.deb"
SHA256 = "bd5df93cf2bee4be40899890f70fd37c2e04cdc0541aaa4952bd1d6258db5726"
RELATIVE = "/pool/universe/c/cgal/" + FILENAME
MIRRORS = ["https://mirrors.tuna.tsinghua.edu.cn/ubuntu", "https://mirrors.kernel.org/ubuntu", "https://archive.ubuntu.com/ubuntu"]
LINUX_CACHE = "/tmp/dip-poly03-cgal-5.4-bd5df93c"
TARGET = ROOT / "local/poly03/cgal/cgal_worker"
DISTRO = os.environ.get("POLY03_CGAL_WSL", "Ubuntu-22.04")


def linux_path(path):
    p=Path(path).resolve()
    if os.name != "nt":
        return str(p)
    return "/mnt/"+p.drive[0].lower()+p.as_posix()[2:]


def kernel_command(*args):
    if os.name == "nt":
        return ["wsl.exe","-d",DISTRO,"--exec",*args]
    return list(args)


def run(*args):
    result=subprocess.run(kernel_command(*args),check=True,stdout=subprocess.PIPE)
    return result.stdout.decode("utf-8",errors="replace").strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline",action="store_true")
    opts=parser.parse_args()
    archive=ROOT/"data/poly03/cgal"/FILENAME
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        if opts.offline:
            raise FileNotFoundError(archive)
        errors=[]
        for mirror in MIRRORS:
            url=mirror+RELATIVE
            try:
                req=urllib.request.Request(url,headers={"User-Agent":"POLY03 CGAL reference builder"})
                with urllib.request.urlopen(req,timeout=25) as response:
                    data=response.read(6_000_000)
                if hashlib.sha256(data).hexdigest()!=SHA256:
                    raise ValueError("Unexpected package digest")
                archive.write_bytes(data)
                break
            except (OSError,ValueError) as exc:
                errors.append((url,str(exc)))
        else:
            raise RuntimeError(errors)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:
        raise ValueError("Unexpected local CGAL package digest")
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    run("mkdir","-p",LINUX_CACHE)
    run("dpkg-deb","-x",linux_path(archive),LINUX_CACHE)
    source=Path(__file__).with_name("cgal_worker.cpp")
    args=["g++","-O2","-std=c++17","-DNDEBUG","-frounding-math","-I"+LINUX_CACHE+"/usr/include",
          linux_path(source),"-lgmp","-lmpfr","-o",linux_path(TARGET)]
    run(*args)
    metadata=dict(package=FILENAME,sha256=SHA256,ubuntu_release="22.04",
                  source_sha256=hashlib.sha256(source.read_bytes().replace(b"\r\n",b"\n")).hexdigest(),
                  binary_sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest(),
                  compiler=run("g++","--version").splitlines()[0],
                  dependency_versions=run("dpkg-query","-W","libboost-dev","libgmp-dev","libmpfr-dev").splitlines(),
                  compiler_arguments=args,upstream="CGAL::Polyline_simplification_2::simplify",wsl=DISTRO if os.name=="nt" else None)
    path=TARGET.with_name("build.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(metadata,indent=2))


if __name__=="__main__":
    main()
