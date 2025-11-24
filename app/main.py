from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import os
import sys
import shutil
import tempfile
import subprocess
import pathlib
import glob
import zipfile
import logging
from datetime import datetime

app = FastAPI(title="FastAPI 文件处理服务", version="0.1.0")

# 模块顶部
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    filename='/home/nan.li/work/fastapi_zip_service/app/fastapi_log.log',
    filemode='a',
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s"))
    logger.addHandler(_handler)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _cleanup_dir(path: str) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        # 忽略清理异常，避免影响响应
        pass


def _save_upload(upload: UploadFile, dst_path: str) -> None:
    # 以流式方式保存，避免一次性读入内存
    with open(dst_path, "wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


# 将临时工作目录放在项目根目录：/home/nan.li/work/fastapi_zip_service
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUN_PREFIX = "fastapi_zip_service_"


def _make_tmp_root() -> str:
    _ensure_dir(PROJECT_ROOT)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"{RUN_PREFIX}{ts}_"
    return tempfile.mkdtemp(prefix=prefix, dir=PROJECT_ROOT)


def _zip_directory(src_dir: str, zip_out_path: str) -> str:
    """将整个目录 src_dir 打包为 zip 文件 zip_out_path。
    保留顶层目录名称为 zip 内的根目录。
    """
    # 若传入 zip_out_path 已包含 .zip 后缀，去掉以供 make_archive 使用
    base_name = zip_out_path[:-4] if zip_out_path.endswith(".zip") else zip_out_path
    parent = os.path.dirname(src_dir)
    base_dir = os.path.basename(src_dir)
    return shutil.make_archive(base_name, "zip", root_dir=parent, base_dir=base_dir)


@app.post("/process")
async def process_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="待处理的文件"),
    output_ext: str = Form(default="md", description="输出文件扩展名，默认 md"),
    processor: str = Form(default="basic", description="处理方式：basic|mineru，默认 basic"),
    mineru_backend: str = Form(default="vlm-transformers", description="当 processor=mineru 时指定后端，如 vlm-transformers"),
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件或文件名为空")

    output_ext = (output_ext or "zip").strip().lower()
    if not output_ext:
        output_ext = "zip"

    # 临时工作目录
    tmp_root = _make_tmp_root()
    in_dir = os.path.join(tmp_root, "input")
    out_dir = os.path.join(tmp_root, "output")
    _ensure_dir(in_dir)
    _ensure_dir(out_dir)
    logger.info(f"in_dir: {in_dir}")
    logger.info(f"out_dir: {out_dir}")

    # 保存上传文件
    in_path = os.path.join(in_dir, pathlib.Path(file.filename).name)
    _save_upload(file, in_path)

    base = pathlib.Path(in_path).stem

    # 如果指定使用 MinerU，则调用 mineru CLI 生成 Markdown
    if processor.strip().lower() == "mineru":
        if not in_path.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="当 processor=mineru 时仅支持 PDF 文件")

        # 指定 mineru 输出目录为 out_dir
        mineru_cmd = [
            "mineru",
            "-p",
            in_path,
            "-o",
            out_dir,
            "-b",
            mineru_backend,
        ]

        proc = subprocess.run(mineru_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err_msg = (proc.stderr or proc.stdout or "未知错误").strip()
            raise HTTPException(status_code=500, detail=f"mineru 处理失败: {err_msg}")

        # 查找 mineru 生成的 .md 文件（通常位于 out_dir/<pdf名>/vlm/<pdf名>.md）
        md_candidates = glob.glob(os.path.join(out_dir, "**", "*.md"), recursive=True)
        target_md = None
        preferred_name = f"{base}.md"
        for md in md_candidates:
            if pathlib.Path(md).name == preferred_name:
                target_md = md
                break
        if target_md is None and md_candidates:
            target_md = md_candidates[0]

        if not target_md or not os.path.exists(target_md):
            raise HTTPException(status_code=500, detail="未找到 mineru 生成的 Markdown 文件")

        return FileResponse(target_md, media_type="text/markdown", filename=pathlib.Path(target_md).name)

    # 默认 basic：调用内部脚本生成 zip 或文本文件
    out_filename = f"{base}.{output_ext}"
    out_path = os.path.join(out_dir, out_filename)

    # 处理脚本路径（位于 ../scripts/process_file.py）
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "process_file.py"))
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail="处理脚本不存在")

    # 调用外部 Python 脚本执行处理逻辑
    cmd = [sys.executable, script_path, "--input", in_path, "--output", out_path, "--ext", output_ext]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        err_msg = (proc.stderr or proc.stdout or "未知错误").strip()
        raise HTTPException(status_code=500, detail=f"处理失败: {err_msg}")

    # 响应返回后清理临时目录
    # 设置媒体类型
    media_type = "application/octet-stream"
    if output_ext == "zip":
        media_type = "application/zip"
    elif output_ext == "md":
        media_type = "text/markdown"
    elif output_ext in ("txt", "csv"):
        media_type = "text/plain"
    elif output_ext == "json":
        media_type = "application/json"

    return FileResponse(out_path, media_type=media_type, filename=out_filename)


@app.post("/process/zip")
async def process_zip(
    file: UploadFile = File(..., description="待处理的 PDF 文件"),
    processor: str = Form(default="mineru", description="处理方式，仅支持 mineru"),
    mineru_backend: str = Form(default="vlm-transformers", description="mineru 后端，如 vlm-transformers"),
):
    """上传 PDF，调用 mineru 处理，并将整个输出目录打包为 ZIP 返回。"""
    if processor.strip().lower() != "mineru":
        raise HTTPException(status_code=400, detail="/process/zip 仅支持 processor=mineru")
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件或文件名为空")

    tmp_root = _make_tmp_root()
    in_dir = os.path.join(tmp_root, "input")
    out_dir = os.path.join(tmp_root, "output")
    _ensure_dir(in_dir)
    _ensure_dir(out_dir)
    logger.info(f"in_dir: {in_dir}")
    logger.info(f"out_dir: {out_dir}")
    in_path = os.path.join(in_dir, pathlib.Path(file.filename).name)
    _save_upload(file, in_path)

    base = pathlib.Path(in_path).stem

    # 调用 mineru 生成输出目录
    in_lower = in_path.lower()
    if in_lower.endswith(".pdf"):
        mineru_input = in_path
    elif in_lower.endswith(".docx") or in_lower.endswith(".doc"):
        mineru_input = _convert_to_pdf(in_path, out_dir)
        logger.info(f"doc/docx 转 PDF 完成: {mineru_input}")
    else:
        raise HTTPException(status_code=400, detail="仅支持 PDF 或 doc/docx（将自动转为 PDF）")

    mineru_cmd = [
        "mineru",
        "-p",
        mineru_input,
        "-o",
        out_dir,
        "-b",
        mineru_backend,
    ]
    logger.info(f"mineru 命令: {' '.join(mineru_cmd)}")
    print(f"print mineru 命令: {' '.join(mineru_cmd)}")
    proc = subprocess.run(mineru_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or "未知错误").strip()
        raise HTTPException(status_code=500, detail=f"mineru 处理失败: {err_msg}")

    # 期望输出目录：out_dir/<base>
    doc_dir = os.path.join(out_dir, base)
    if not os.path.isdir(doc_dir):
        # 如果结构不同，兜底尝试查找包含 base 的目录
        candidates = [d for d in glob.glob(os.path.join(out_dir, "**"), recursive=True) if os.path.isdir(d)]
        doc_dir = next((d for d in candidates if os.path.basename(d) == base), None)
    if not doc_dir or not os.path.isdir(doc_dir):
        raise HTTPException(status_code=500, detail="未找到 mineru 输出目录")

    zip_out = os.path.join(out_dir, f"{base}.zip")
    zip_path = _zip_directory(doc_dir, zip_out)

    return FileResponse(zip_path, media_type="application/zip", filename=os.path.basename(zip_path))


@app.post("/zip_dir")
async def zip_dir(
    dir_path: str = Form(..., description="要打包的目录路径，仅允许 /tmp/fastapi_zip_service_* 前缀"),
):
    """直接根据提供的临时目录路径打包并返回 ZIP。用于你给出的路径场景。"""
    # 仅允许打包项目根目录下的临时工作目录
    prefix = PROJECT_ROOT + os.sep
    norm = os.path.abspath(dir_path)
    if not norm.startswith(prefix):
        raise HTTPException(status_code=400, detail=f"仅允许打包位于 {PROJECT_ROOT} 下的临时目录")
    if not os.path.isdir(norm):
        raise HTTPException(status_code=404, detail="目录不存在")

    parent = os.path.dirname(norm)
    base = os.path.basename(norm)
    zip_out = os.path.join(parent, f"{base}.zip")
    zip_path = _zip_directory(norm, zip_out)
    return FileResponse(zip_path, media_type="application/zip", filename=os.path.basename(zip_path))


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/")
async def root():
    return JSONResponse({"message": "FastAPI 文件处理服务运行中", "docs": "/docs"})


def _convert_to_pdf(src_path: str, out_dir: str) -> str:
    """使用 LibreOffice 将 doc/docx 转换为 pdf，返回生成的 pdf 路径。"""
    _ensure_dir(out_dir)
    base = pathlib.Path(src_path).stem
    pdf_path = os.path.join(out_dir, f"{base}.pdf")
    cmd = [
        "libreoffice", "--headless",
        "--convert-to", "pdf",
        "--outdir", out_dir,
        src_path,
    ]
    logger.info(f"convert cmd: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(pdf_path):
        err_msg = (proc.stderr or proc.stdout or "未知错误").strip()
        raise HTTPException(status_code=500, detail=f"文档转 PDF 失败: {err_msg}")
    return pdf_path