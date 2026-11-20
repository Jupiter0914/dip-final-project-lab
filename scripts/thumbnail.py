"""Second candidate, tested only on real development masks. Area-preserving one-bit preview."""
import cv2
import numpy as np
from study import ROOT,inputs,read_csv,save_csv,silhouette,metrics


def main():
    records=[]
    for src in read_csv(ROOT/"records/samples.csv"):
        if src["partition"]!="dev":
            continue
        target,_,_=silhouette(inputs(src))
        for scale in (4,8):
            h,w=target.shape
            ph,pw=(-h)%scale,(-w)%scale
            padded=np.pad(target,((0,ph),(0,pw)))
            counts=padded.reshape(padded.shape[0]//scale,scale,-1,scale).mean(axis=(1,3))
            sims={"nearest":padded[scale//2::scale,scale//2::scale]}
            for threshold in (.35,.45,.50,.55,.65):
                sims[f"fixed_{threshold:.2f}"]=(counts>=threshold)
            n=round(float(counts.sum()))
            sel=np.zeros(counts.size,np.uint8)
            sel[np.argsort(-counts.ravel(),kind="stable")[:n]]=1
            sims["area_matched"]=sel.reshape(counts.shape)
            records.append(dict(id=src["id"],scale=scale,method="input",iou=1.0,area_bias=0.0))
            for method,small in sims.items():
                recovered=small.astype(np.uint8).repeat(scale,axis=0).repeat(scale,axis=1)[:h,:w]
                result=metrics(target,recovered)
                records.append(dict(id=src["id"],scale=scale,method=method,iou=result["iou"],
                                area_bias=(result["fp"]-result["fn"])/result["reference_pixels"]))
    save_csv(ROOT/"results/thumbnail/per_image.csv",records)


if __name__=="__main__":
    main()
