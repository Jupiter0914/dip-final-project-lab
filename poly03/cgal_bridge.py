"""Call CGAL's simultaneous closed-polyline simplifier through one persistent local process."""
import atexit
import struct
import subprocess
import threading
import time
import numpy as np
from .cgal_build import TARGET, kernel_command, linux_path

_LOCK=threading.Lock()
_PROC=None


def _read(stream,n):
    parts=[]
    remaining=n
    while remaining:
        raw=stream.read(remaining)
        if not raw:
            raise RuntimeError("CGAL worker terminated. See local/poly03/cgal/worker.log")
        parts.append(raw)
        remaining-=len(raw)
    return b"".join(parts)


def _start():
    global _PROC
    if _PROC is not None and _PROC.poll() is None:
        return _PROC,0.0
    if not TARGET.is_file():
        raise FileNotFoundError("Build the CGAL worker with python -m poly03.cgal_build")
    start=time.perf_counter_ns()
    with TARGET.with_name("worker.log").open("ab") as log:
        _PROC=subprocess.Popen(kernel_command(linux_path(TARGET)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                               stderr=log,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if _read(_PROC.stdout,4)!=b"CG54":
        raise RuntimeError("Unexpected CGAL worker handshake")
    return _PROC,(time.perf_counter_ns()-start)/1e6


def close():
    global _PROC
    with _LOCK:
        if _PROC is not None:
            _PROC.stdin.close()
            try:
                _PROC.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _PROC.terminate()
                _PROC.wait(timeout=5)
            _PROC=None


atexit.register(close)


def simplify(rings,target_vertices,*,cost="squared"):
    """Return simplified rings in original order and a diagnostic record. Input rings are disjoint, simple lattice rings."""
    start=time.perf_counter_ns()
    n=int(target_vertices)
    names={"squared":0,"scaled":1}
    if cost not in names or n<0 or n>=2**32:
        raise ValueError("Invalid cost or target")
    pieces=[]
    for ring in rings:
        points=np.asarray(ring)
        if points.ndim!=2 or points.shape[1]!=2 or len(points)<3 or points.dtype.kind not in "iu":
            raise ValueError("Expected a closed ring of at least three integer XY vertices; omit the repeated endpoint")
        if np.array_equal(points[0],points[-1]) or np.any(points< -(2**31)) or np.any(points>=2**31):
            raise ValueError("Repeated closure or coordinate outside int32")
        pieces.append(np.ascontiguousarray(points,dtype="<i4"))
    if not pieces:
        raise ValueError("At least one ring is required")
    total=sum(map(len,pieces))
    record=dict(backend="CGAL 5.4",cost=cost,input_vertices=total,output_vertices=0,target_vertices=n,
                startup_ms=0.0,triangulation_ms=0.0,native_ms=0.0)
    if n<3*len(pieces):
        record.update(status="below_ring_count_bound",elapsed_ms=(time.perf_counter_ns()-start)/1e6)
        return [],record
    request=[struct.pack("<III",len(pieces),n,names[cost])]
    for points in pieces:
        request.extend((struct.pack("<I",len(points)),points.tobytes()))
    with _LOCK:
        proc,startup=_start()
        proc.stdin.write(b"".join(request))
        proc.stdin.flush()
        error,count=struct.unpack("<II",_read(proc.stdout,8))
        record["startup_ms"]=startup
        if error:
            record.update(status="cgal_rejected",reason=_read(proc.stdout,count).decode(errors="replace"),
                          elapsed_ms=(time.perf_counter_ns()-start)/1e6)
            return [],record
        record["triangulation_ms"],record["native_ms"]=struct.unpack("<dd",_read(proc.stdout,16))
        if count!=len(pieces):
            raise RuntimeError("Lost CGAL ring identity")
        out=[]
        for _ in range(count):
            size=struct.unpack("<I",_read(proc.stdout,4))[0]
            coords=np.frombuffer(_read(proc.stdout,8*size),dtype="<i4").reshape(size,2).copy()
            out.append(coords)
    count=sum(map(len,out))
    if any(len(r)<3 for r in out): status="degenerate_output"
    elif count>n: status="stopped_above_target"
    else: status="ok"
    record.update(output_vertices=count,status=status,elapsed_ms=(time.perf_counter_ns()-start)/1e6)
    return out,record
