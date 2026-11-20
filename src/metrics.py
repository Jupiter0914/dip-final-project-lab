"""Full native-image region overlap and symmetric two-pixel boundary F."""
import cv2
import numpy as np


def metrics(mask,out):
    a,b = cv2.countNonZero(mask),cv2.countNonZero(out)
    hit = cv2.countNonZero(cv2.bitwise_and(mask,out))
    fn,fp = a-hit,b-hit
    kernel = np.ones((3,3),np.uint8)
    def boundary(x):
        eroded = cv2.erode(x,kernel,borderType=cv2.BORDER_CONSTANT,borderValue=0)
        return x-eroded
    ref,pred = boundary(mask),boundary(out)
    def matched(source,target):
        distance = cv2.distanceTransform(1-target,cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
        return float(np.count_nonzero((source != 0) & (distance<=2))) / max(cv2.countNonZero(source),1)
    recall,precision = matched(ref,pred), matched(pred,ref)
    return dict(iou=hit/(a+b-hit),xor_pixels=fp+fn,fp=fp,fn=fn,reference_pixels=a,
                boundary_f2=2*precision*recall/max(precision+recall,1e-20))
