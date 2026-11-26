"""读图引擎 v1。协议结果走标准输出，诊断由调用方从标准错误收集。"""
import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, allow_nan=False), flush=True)


class Parser(argparse.ArgumentParser):
    def print_help(self, file=None):
        emit("help", message=self.format_help())

    def error(self, message):
        raise ValueError(message)


def read_pages(value, total):
    if not value:
        return list(range(1, total + 1))
    pages = set()
    for part in value.split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part.strip())
        if not match:
            raise ValueError("页码格式应为 1、1-7 或 1,3-5。")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= total:
            raise ValueError(f"页码超出范围，本文件共 {total} 页。")
        pages.update(range(first, last + 1))
    return sorted(pages)


@contextmanager
def output_lock(directory):
    import msvcrt
    with (directory / ".ocr.lock").open("a+b") as handle:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise ValueError("此输出目录已有读图任务。") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class Progress(dict):
    def update(self, **values):
        super().update(values)
        fields = {k: self[k] for k in ("tile", "tileCount", "page", "cachedTiles", "cachedRowGroups")}
        if self.get("document") is not None:
            fields["document"] = self["document"]
        emit("progress", **fields)


def ocr(args):
    import multiprocessing
    import pymupdf
    from 并行读图 import process
    if not 0 <= args.threshold <= 255 or not 1 <= args.parallel <= 61:
        raise ValueError("阈值范围为 0～255，并行数范围为 1～61。")
    if len(args.pdf) != len(args.out):
        raise ValueError("每个 --pdf 都需要一个对应的 --out，按传入顺序配对。")
    if args.document_pages and (args.pages or len(args.document_pages) != len(args.pdf)):
        raise ValueError("每份 PDF 需对应一组页码。")
    outputs = [path.resolve() for path in args.out]
    if len(set(outputs)) != len(outputs):
        raise ValueError("每份图纸需要独立的输出目录。")
    batch = len(outputs) > 1
    specs = []
    documents = []
    for index, (path, out) in enumerate(zip(args.pdf, outputs), 1):
        pdf = path.resolve(strict=True)
        if not pdf.is_file():
            raise ValueError(f"请指定 PDF 文件：{pdf}")
        with pymupdf.open(pdf) as doc:
            numbers = read_pages(args.document_pages[index - 1] if args.document_pages else args.pages, len(doc))
            if doc.needs_pass or not numbers:
                raise ValueError(f"图纸加密或没有可读页：{pdf}")
        with pdf.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        cache = out / ".ocr_v1" / digest / str(args.threshold)
        documents.append(dict(document=index, pdf=str(pdf), out=str(out), pages=numbers))
        specs.extend(dict(file=str(pdf), page=n, force=args.force, threshold=args.threshold,
                          cache=str(cache / str(n)), out=out, document=index if batch else None)
                     for n in numbers)
    # GUI 客户端通过管道收事件，子进程用无控制台解释器加载同一套模型。
    multiprocessing.set_executable(str(ROOT / "运行库/pythonw.exe"))

    def publish(spec, result):
        target = spec["out"] / f"page_{spec['page']}.json"
        temp = target.with_suffix(".partial")
        temp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)
        fields = dict(page=spec["page"], file=str(target))
        if batch:
            fields["document"] = spec["document"]
        emit("page", **fields)

    with ExitStack() as locks:
        for out in sorted(outputs):
            out.mkdir(parents=True, exist_ok=True)
            locks.enter_context(output_lock(out))
        process(specs, args.parallel, Progress(), lambda job: None, publish)
    if batch:
        return {"documents": documents, "parallel": args.parallel}
    return {"pages": documents[0]["pages"], "parallel": args.parallel}


def crop(args):
    import pymupdf
    coordinates = [float(v) for v in args.bbox.split(",")]
    if len(coordinates) != 4 or not all(math.isfinite(v) for v in [*coordinates, args.pad]) or args.pad < 0:
        raise ValueError("需要四个有限点坐标和非负留白。")
    x, y, r, b = coordinates
    if x >= r or y >= b:
        raise ValueError("坐标必须为左、上、右、下。")
    if args.out.resolve() == args.pdf or args.out.suffix.lower() != ".png":
        raise ValueError("请指定独立的 PNG 输出文件。")
    with pymupdf.open(args.pdf) as doc:
        if not 1 <= args.page <= len(doc) or doc.needs_pass:
            raise ValueError("页面不存在或图纸需要密码。")
        page = doc[args.page - 1]
        if (page.rect & pymupdf.Rect(x, y, r, b)).is_empty:
            raise ValueError("所选区域位于图幅外。")
        pad = args.pad
        clip = page.rect & pymupdf.Rect(x-pad, y-pad, r+pad, b+pad)
        data = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip, alpha=False).tobytes("png")
    import tempfile
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.out.parent, suffix=".partial", delete=False) as temp:
        temp.write(data)
    os.replace(temp.name, args.out)
    return dict(page=args.page, bbox=list(clip), file=str(args.out.resolve()))


def selftest(args):
    import numpy as np
    import pymupdf
    from PIL import Image
    import 并行读图 as parallel
    parallel.init_worker()
    with Image.open(ROOT / "自检样图.png") as image:
        rows, _ = parallel.engine(np.asarray(image.convert("RGB")), use_cls=False)
    text = " ".join(row[1] for row in rows or [])
    if "OCRTEST12345" not in "".join(text.upper().split()):
        raise RuntimeError(f"自检样图识别未通过，读到 {text!r}。")
    return dict(text=text, python=sys.version.split()[0])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    os.environ["TEMP"] = os.environ["TMP"] = str(ROOT)
    parser = Parser(prog="读图引擎")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ocr")
    p.add_argument("--pdf", type=Path, action="append", required=True, help="可重复传入，顺序与 --out 对应")
    p.add_argument("--out", type=Path, action="append", required=True, help="每份 PDF 使用独立的输出目录")
    p.add_argument("--pages")
    p.add_argument("--document-pages", action="append", help="每份 PDF 的待识别页码，顺序与 --pdf 对应")
    p.add_argument("--parallel", type=int, default=min(4, os.cpu_count() or 1))
    p.add_argument("--threshold", type=int, default=165)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("crop")
    p.add_argument("--pdf", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--page", type=int, required=True)
    p.add_argument("--bbox", required=True)
    p.add_argument("--pad", type=float, default=12)
    sub.add_parser("selftest")
    start = time.monotonic()
    try:
        argv = sys.argv[1:]
        if "--bbox" in argv:
            i = argv.index("--bbox")
            if i + 1 < len(argv):
                argv[i:i+2] = ["--bbox=" + argv[i+1]]
        args = parser.parse_args(argv)
        if args.command == "crop":
            args.pdf = args.pdf.resolve(strict=True)
            if not args.pdf.is_file():
                raise ValueError("请指定 PDF 文件。")
        result = {"ocr": ocr, "crop": crop, "selftest": selftest}[args.command](args)
        emit("done", seconds=round(time.monotonic()-start, 3), **result)
    except (Exception, KeyboardInterrupt) as exc:
        emit("error", message=str(exc) or "读图已中断。")
        return 1
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())

