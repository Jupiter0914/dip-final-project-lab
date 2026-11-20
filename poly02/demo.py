"""Live local polygon demonstration and portable snapshots made from real decoded POL1 files."""
import argparse
import base64
import io
import json
import struct
import urllib.parse
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from src.codec import encode,decode
from .core import exterior,fit,metrics
from .data import ROOT,OUT,REC,CFG,rows,read_mask
from .run import execute

METHODS=["geometry","local_iou","sm_iou","raster","post_xor","post_guard"]
KS=[8,12,16,24,32,48]
BG=(249,248,243)
FG=(61,76,79)
FP=(209,92,44)
FN=(34,133,166)
GREEN=(17,115,84)


def b64(raw): return base64.b64encode(raw).decode("ascii")


def png(im):
    f=io.BytesIO()
    im.save(f,format="PNG")
    return "data:image/png;base64,"+b64(f.getvalue())


def display(mask,pred=None,points=None):
    rgb=np.empty((*mask.shape,3),np.uint8)
    rgb[:]=BG
    if pred is None:
        rgb[mask!=0]=FG
    else:
        rgb[(mask==1)&(pred==1)]=FG
        rgb[pred>mask]=FP
        rgb[pred<mask]=FN
    im=Image.fromarray(rgb)
    if points is not None:
        d=ImageDraw.Draw(im)
        coords=[tuple(map(int,p)) for p in points]
        d.line(coords+[coords[0]],fill=(10,164,113),width=2)
        for x,y in coords: d.ellipse((x-3,y-3,x+3,y+3),fill=(255,211,78),outline=(34,50,38),width=1)
    return im


def move_witness(mask,item):
    points=[np.asarray(item[k],np.int32) for k in ("before","after")]
    blobs=[encode(mask.shape,p) for p in points]
    outputs=[decode(b) for b in blobs]
    scores=[metrics(mask,p) for p in outputs]
    j=item["vertex"]
    x,y=points[1][j]
    old=points[0][j]
    # Magnify the moved endpoint; the printed errors still refer to the whole image.
    xvals=[int(x),int(old[0])]
    yvals=[int(y),int(old[1])]
    side=max(23,max(xvals)-min(xvals)+16,max(yvals)-min(yvals)+16)
    h,w=mask.shape
    x0=max(0,min(w-side,(min(xvals)+max(xvals)-side)//2))
    y0=max(0,min(h-side,(min(yvals)+max(yvals)-side)//2))
    rect=(x0,y0,min(w,x0+side),min(h,y0+side))
    pics=[]
    for p,pred in zip(points,outputs):
        im=display(mask,pred)
        d=ImageDraw.Draw(im)
        xy=tuple(map(int,p[j]))
        d.ellipse((xy[0]-2,xy[1]-2,xy[0]+2,xy[1]+2),outline=(160,36,126),width=2)
        pics.append(png(im.crop(rect)))
    return dict(accepted=bool(item["accepted"]),vertex=j+1,step=item["step"],sweep=item["sweep"]+1,
                old=item["old_xy"],new=item["new_xy"],floor=item["floor"],crop=rect,before=scores[0],after=scores[1],
                before_image=pics[0],after_image=pics[1],before_poly=b64(blobs[0]),after_poly=b64(blobs[1]))


def compute(raw,name,k):
    if k not in KS: raise ValueError("Unsupported K")
    cfg=json.loads(CFG.read_text())
    mask,c=exterior(raw,k)
    result={}
    renderings={}
    occupied=raw.copy()
    for method in METHODS:
        blob,scores=execute(raw,k,method,cfg)
        p=np.frombuffer(blob,offset=10,dtype="<u2").reshape(-1,2)
        pred=decode(blob)
        result[method]=dict(scores=scores,polygon=b64(blob),vertices=p.tolist())
        renderings[method]=(p,pred)
        occupied|=pred
    ys,xs=np.nonzero(occupied)
    pad=max(8,int(.06*max(xs.max()-xs.min(),ys.max()-ys.min())))
    rect=(max(0,int(xs.min())-pad),max(0,int(ys.min())-pad),
          min(mask.shape[1],int(xs.max())+pad+1),min(mask.shape[0],int(ys.max())+pad+1))
    for method,(p,pred) in renderings.items():
        result[method].update(vertex_image=png(display(mask,points=p).crop(rect)),error_image=png(display(mask,pred).crop(rect)))
    trace=[]
    v,_=fit(mask,c,k,"post_guard",cfg,trace=trace)
    assert b64(encode(mask.shape,v))==result["post_guard"]["polygon"]
    witnesses=[]
    for accepted in (True,False):
        group=[r for r in trace if r["accepted"]==accepted]
        if group:
            item=max(group,key=lambda r:r["before_cost"]-r["trial_cost"])
            witnesses.append(move_witness(mask,item))
    return dict(id=name,k=k,w=mask.shape[1],h=mask.shape[0],view_crop=rect,input=png(display(raw).crop(rect)),target=png(display(mask).crop(rect)),
                methods=result,moves=witnesses)


def catalog():
    return {r["id"]:r for r in rows(REC/"samples.csv")}


def default_case():
    path=OUT/"cases.csv"
    if path.exists():
        row=next((r for r in rows(path) if r["reason"]=="boundary_rescue"),None)
        if row: return row["id"],int(row["k"])
    return next(iter(catalog())),16


def template(payload):
    return Path(__file__).with_name("demo.html").read_text(encoding="utf-8").replace("/*DATA*/null",
        json.dumps(payload,ensure_ascii=False,separators=(",",":")).replace("<","\\u003c"))


def export(directory):
    directory.mkdir(exist_ok=True,parents=True)
    name,k=default_case()
    raw=read_mask(catalog()[name])
    examples={str(b):compute(raw,name,b) for b in (16,32)}
    (directory/"demo.html").write_text(template(dict(offline=True,ids=[name],initial=name,k=k,examples=examples)),encoding="utf-8")
    witness=examples[str(k)]
    export_info=dict(id=name,k=k,methods={m:{key:val for key,val in s.items() if key in ("vertices","scores")} for m,s in witness["methods"].items()},moves=[])
    for m,s in witness["methods"].items(): (directory/(m+".poly")).write_bytes(base64.b64decode(s["polygon"]))
    for move in witness["moves"]:
        label="accepted" if move["accepted"] else "rejected"
        for side in ("before","after"):
            (directory/(label+"-"+side+".poly")).write_bytes(base64.b64decode(move[side+"_poly"]))
        export_info["moves"].append({key:val for key,val in move.items() if not key.endswith(("_image","_poly"))})
    (directory/"witness.json").write_text(json.dumps(export_info,indent=2),encoding="utf-8")
    print(name,k,len(witness["moves"]),"real move examples")


def serve(port,open_tab):
    sources=catalog()
    name,k=default_case()
    @lru_cache(maxsize=12)
    def calculate(i,b): return compute(read_mask(sources[i]),i,b)
    class Handler(BaseHTTPRequestHandler):
        def send_data(self,content,mime,status=200):
            self.send_response(status)
            self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def do_GET(self):
            parts=urllib.parse.urlsplit(self.path)
            q=urllib.parse.parse_qs(parts.query)
            if parts.path=="/":
                html=template(dict(offline=False,ids=list(sources),initial=name,k=k))
                self.send_data(html.encode(),"text/html; charset=utf-8")
            elif parts.path=="/run":
                try:
                    data=calculate(q["id"][0],int(q["k"][0]))
                    self.send_data(json.dumps(data).encode(),"application/json")
                except (ValueError,KeyError,IndexError) as exc: self.send_data(str(exc).encode(),"text/plain",400)
            else: self.send_data(b"Not found","text/plain",404)
        def do_POST(self):
            try:
                parts=urllib.parse.urlsplit(self.path)
                if parts.path!="/run": raise ValueError("Use /run")
                q=urllib.parse.parse_qs(parts.query)
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=8_000_000: raise ValueError("Choose a PNG under 8 MB")
                with Image.open(io.BytesIO(self.rfile.read(size))) as im:
                    if im.format!="PNG" or im.mode not in ("1","L","P","I","I;16") or im.width*im.height>4_000_000:
                        raise ValueError("Choose a single-channel binary PNG up to 4 megapixels")
                    raw=np.asarray(np.asarray(im)!=0,np.uint8)
                self.send_data(json.dumps(compute(raw,"本地二值图",int(q["k"][0]))).encode(),"application/json")
            except (OSError,ValueError,IndexError,KeyError) as exc: self.send_data(str(exc).encode(),"text/plain; charset=utf-8",400)
    srv=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    url=f"http://127.0.0.1:{srv.server_port}/"
    print(url,flush=True)
    if open_tab: webbrowser.open(url)
    try: srv.serve_forever()
    finally: srv.server_close()


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--export",type=Path,help="Build standalone real-run viewer and POL1 samples")
    p.add_argument("--port",type=int,default=8072)
    p.add_argument("--open",action="store_true")
    a=p.parse_args()
    if a.export: export(a.export)
    else: serve(a.port,a.open)
