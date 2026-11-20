"""Retrieve Oxford annotations, select whole source photos and hash the selected byte streams."""
import argparse
import csv
import hashlib
import io
import json
import shutil
import tarfile
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RECORDS = ROOT / "records"
MD5 = "95a8c909bbe2e81eed6a22bccdf3f68f"
URLS = (
    "https://thor.robots.ox.ac.uk/datasets/pets/annotations.tar.gz",
    "https://www.robots.ox.ac.uk/~vgg/data/pets/data/annotations.tar.gz",
)
SALT = "dip-rings-v1"


def file_hash(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def retrieve(archive):
    if archive.exists():
        if file_hash(archive, "md5") != MD5:
            raise ValueError("Local annotation archive has the wrong MD5")
        return
    partial = archive.with_suffix(".part")
    errors = []
    for url in URLS:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "DIP-course-research/1"})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
                shutil.copyfileobj(response, out)
            if file_hash(partial, "md5") != MD5:
                raise ValueError("Archive checksum mismatch")
            partial.replace(archive)
            (DATA / "retrieved-from.txt").write_text(url+"\n", encoding="utf-8")
            return
        except (OSError, ValueError) as exc:
            errors.append(f"{url} {exc}")
    raise RuntimeError("\n".join(errors))


def rank(value):
    return hashlib.sha256(f"{SALT}|{value}".encode()).hexdigest()


def select(lists):
    by_species = defaultdict(set)
    split_breeds = {}
    for split, metadata in lists.items():
        groups = defaultdict(list)
        for line in metadata.splitlines():
            name, _, species, _ = line.split()
            breed = name.rsplit("_", 1)[0]
            by_species[species].add(breed)
            groups[breed].append(name)
        split_breeds[split] = groups
    dev_breeds = set()
    for species, count in [("1", 4), ("2", 8)]:
        dev_breeds.update(sorted(by_species[species], key=rank)[:count])
    selected = []
    for partition, split, count in [("dev", "trainval", 3), ("confirm", "test", 4)]:
        for breed, names in sorted(split_breeds[split].items()):
            if (breed in dev_breeds) != (partition == "dev"):
                continue
            for name in sorted(names, key=rank)[:count]:
                selected.append(dict(partition=partition, official=split, breed=breed, id=name))
    assert len(selected) == 136 and len({r["id"] for r in selected}) == 136
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Require the checked-in manifest to match")
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    RECORDS.mkdir(exist_ok=True)
    archive = DATA / "annotations.tar.gz"
    retrieve(archive)
    masks = DATA / "trimaps"
    masks.mkdir(exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        lists = {s:tar.extractfile(f"annotations/{s}.txt").read().decode("utf-8") for s in ("trainval","test")}
        rows = select(lists)
        for r in rows:
            member = "annotations/trimaps/"+r["id"]+".png"
            data = tar.extractfile(member).read()
            path = masks / (r["id"] + ".png")
            if not path.exists():
                path.write_bytes(data)
            r["sha256"] = hashlib.sha256(data).hexdigest()
            if file_hash(path) != r["sha256"]:
                raise ValueError(path)
            r["member"] = member
        info = dict(archive="data/annotations.tar.gz", md5=MD5, sha256=file_hash(archive), bytes=archive.stat().st_size,
                    official_lists={s:hashlib.sha256(v.encode()).hexdigest() for s,v in lists.items()}, urls=URLS,
                    partition_rule="sha256(dip-rings-v1|name); 4 cat and 8 dog breeds for dev; 3 trainval sources/breed; other breeds 4 official test sources/breed")
    assert len({r["sha256"] for r in rows}) == len(rows)
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    outputs = {"samples.csv":buf.getvalue(),"data.json":json.dumps(info,indent=2)+"\n"}
    for filename, content in outputs.items():
        path = RECORDS / filename
        if args.check or path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise ValueError(f"Published inventory differs: {filename}")
        else:
            path.write_text(content,encoding="utf-8")
    print(f"{len(rows)} unique source files; 36 development / 100 confirmation. SHA-256 {info['sha256']}")


if __name__ == "__main__":
    main()
