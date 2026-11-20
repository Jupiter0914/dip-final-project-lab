"""Encode a single existing binary silhouette, or decode a POL1 polygon to PNG."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from study import ROOT
from src.codec import silhouette,encode,decode
from src.method import fit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_subparsers(dest="action",required=True)
    enc=modes.add_parser("encode")
    enc.add_argument("source",type=Path)
    enc.add_argument("output",type=Path)
    enc.add_argument("--vertices",type=int,choices=[16,32],default=16)
    enc.add_argument("--oxford",action="store_true",help="Use label 1 only, as in Oxford trimaps")
    enc.add_argument("--method",choices=["rdp","dp","full_dp","geometry","geometry_long","raster"],default="raster")
    dec=modes.add_parser("decode")
    dec.add_argument("source",type=Path)
    dec.add_argument("output",type=Path)
    args=parser.parse_args()
    if args.output.resolve()==args.source.resolve():
        parser.error("Choose a separate output path")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.action=="decode":
        mask=decode(args.source.read_bytes())
        Image.fromarray(255*mask).save(args.output,format="PNG")
        print(f"{mask.shape[1]} x {mask.shape[0]} PNG")
        return
    with Image.open(args.source) as im:
        raw=np.asarray(im)
    if raw.ndim!=2:
        parser.error("Provide a single-channel binary mask or Oxford indexed trimap")
    foreground=raw if args.oxford else np.asarray(raw!=0,np.uint8)
    mask,contour,_=silhouette(foreground)
    params=json.loads((ROOT/"configs/fixed.json").read_text())["methods"][args.method]
    points,_=fit(mask,contour,args.vertices,args.method,**params)
    blob=encode(mask.shape,points)
    args.output.write_bytes(blob)
    print(f"{len(points)} vertices, {len(blob)} bytes")


if __name__=="__main__":
    main()
