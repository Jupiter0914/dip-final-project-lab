"""Generate readable K-specific audit tables from the exact published CSVs."""
from .data import ROOT,OUT,rows
from .figures import LABEL


def main():
    text=["# 按预算的完整结果","",
          "FP 是多填，FN 是漏填。以下计数为每源图平均像素数，质量指标为原尺寸图像的等权均值。编码包含初始化、合法性检查和生成 POL1 字节，解码包含协议校验与回填。",""]
    for stage,title in [("dev","36 张开发照片"),("new","200 张新 Oxford 照片"),("cross","70 个 MPEG-7 类别"),("curve","25 张预定 Oxford 照片的补充预算")]:
        table=rows(OUT/stage/"summary.csv")
        text+=["## "+title,"","| K | 方法 | 字节 | XOR | FP | FN | IoU | BF1 | BF2 | BF3 | 编码 ms | 编码 p95 ms | 解码 ms | 解码 p95 ms |",
               "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for k in sorted({int(r["k"]) for r in table if r["k"]!="all"}):
            for r in table:
                if r["k"]!=str(k): continue
                fields=[str(k),LABEL[r["method"]],str(round(float(r["bytes"])))]
                fields += [f"{float(r[x]):.2f}" for x in ("xor","fp","fn")]
                fields += [f"{float(r[x]):.5f}" for x in ("iou","bf1","bf2","bf3")]
                fields += [f"{float(r[x]):.3f}" for x in ("encode_ms","p95_encode_ms","decode_ms","p95_decode_ms")]
                text.append("| "+" | ".join(fields)+" |")
        text+=["",f"[完整均值、中位数、p95、汇总像素口径](../../results/poly02/{stage}/summary.csv) · [逐图实测](../../results/poly02/{stage}/per_image.csv)","",
               "表中每格按改善 / 持平 / 退化列出源图数。FP、FN、XOR 取减少为改善。","",
               "| K | 方法 / 对照 | XOR | FP | FN | IoU | BF1 | BF2 | BF3 |","|---:|---|---|---|---|---|---|---|---|"]
        a=rows(OUT/stage/"paired_summary.csv")
        index={(r["k"],r["method"],r["baseline"],r["metric"]):r for r in a}
        for kk in sorted({int(r["k"]) for r in a if r["k"]!="all"}):
            for method,base in [("raster","local_iou"),("local_iou","sm_iou"),("post_xor","geometry"),("post_guard","geometry"),("post_guard","post_xor"),("post_guard","local_iou")]:
                fields=[str(kk),LABEL[method]+" / "+LABEL[base]]
                for met in ("saved_xor","saved_fp","saved_fn","iou_pp","bf1_pp","bf2_pp","bf3_pp"):
                    r=index[str(kk),method,base,met]
                    fields.append("/".join(r[k] for k in ("up","tie","down")))
                text.append("| "+" | ".join(fields)+" |")
        text+=["",f"[各预算绝对变化、配对区间及最差源图](../../results/poly02/{stage}/paired_summary.csv) · [逐源差值](../../results/poly02/{stage}/paired.csv)",""]
    f=ROOT/"report/poly02/metrics.md"
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text("\n".join(text).rstrip()+"\n",encoding="utf-8")


if __name__=="__main__": main()
