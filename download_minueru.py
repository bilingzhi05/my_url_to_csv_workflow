import os
import sys
import zipfile
import re
from typing import Optional
import pathlib
import subprocess
try:
    import requests
except ImportError:
    print("缺少依赖: 请先安装 requests —— pip install requests", file=sys.stderr)
    raise

# 依赖本地模块
from my_confluce_test import export_confluence_page_to_pdf_by_url, _safe_filename
from process_client import process_document

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

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
    print(f"convert cmd: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(pdf_path):
        err_msg = (proc.stderr or proc.stdout or "未知错误").strip()
        raise Exception(f"文档转 PDF 失败: {err_msg}")
    return pdf_path

class SkipProcessing(Exception):
    """输出目录已存在，跳过本轮处理。"""
    pass

def url_to_zip(
    page_url: str,
    processor: str = "mineru",
    server_url: str = "http://10.58.11.60:7890/process/zip",
    pdf_out: Optional[str] = None,
    md_out: Optional[str] = None,
    timeout: int = 6000,
    webhook_url: Optional[str] = "http://localhost:5678/webhook-test/b417dcab-96b5-437e-816e-666ea406e4a0",
) -> str:
    """
    给定 Confluence 页面 URL：
    1) 导出 PDF 到本地
    2) 上传到处理服务并获取 Markdown
    3) 返回 Markdown 文本，并可选落盘

    :param page_url: Confluence 页面完整 URL
    :param processor: 处理器名称（默认 mineru）
    :param server_url: 处理服务 URL
    :param pdf_out: 可选，PDF 输出路径（不提供则自动按标题命名）
    :param md_out: 可选，Markdown 输出路径（默认 output.md）
    :param timeout: 总体请求超时时长（秒）
    :return: mineru 解析出来的zip 文件路径
    """
    pdf_path = ''
    # 1) 从 URL 导出 PDF
    print(f"开始导出 PDF，URL: {page_url}")
    if not page_url or not page_url.strip():
        raise ValueError("Confluence 页面 URL 不能为空")
    if not page_url.startswith("https://"):
        pdf_path = save_with_sanitized_name(page_url)
        print(f"导出本地文件路径: {pdf_path}")
    else:
        try:
            pdf_path = export_confluence_page_to_pdf_by_url(page_url, (pdf_out if pdf_out and pdf_out.strip() else None))
        except Exception as e:
            # 回退：根据 URL 推断本地已存在的 PDF 文件名
            try:
                # 解析标题
                parts = page_url.split("/display/")
                space_and_title = parts[1].split("/") if len(parts) == 2 else []
                title = space_and_title[1].replace("+", " ") if len(space_and_title) == 2 else "confluence_page"
                candidate = _safe_filename(title) + ".pdf"
                candidate_abs = os.path.abspath(candidate)
                if os.path.isfile(candidate_abs):
                    pdf_path = candidate_abs
                    print(f"导出失败，使用本地现有 PDF: {pdf_path}\n原因: {e}")
                else:
                    raise
            except Exception:
                raise e

    if not pdf_path or not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"未找到导出的 PDF 文件: {pdf_path}")
    if not pdf_path.endswith(".pdf"):
        tmp_path = _convert_to_pdf(pdf_path, os.path.dirname(pdf_path))
        print(f"文件转换{pdf_path} --> {tmp_path}")
        pdf_path = tmp_path

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    root_dir = os.path.dirname(pdf_path)
    save_dir = os.path.join(root_dir, base_name)
    # 若该 URL 对应的输出目录已存在，直接跳过
    if os.path.isdir(save_dir):
        msg = f"输出目录已存在，跳过: {save_dir}"
        print(msg)
        raise SkipProcessing(msg)
    os.makedirs(save_dir, exist_ok=True)
    print(f"PDF 路径: {pdf_path}")
    
    # 2) 上传 PDF 到处理服务，获取 ZIP
    requested_out = (md_out if md_out and md_out.strip() else "output.zip")
    zip_filename = os.path.basename(requested_out)
    zip_output_path = os.path.join(save_dir, zip_filename)
    print(f"开始上传到处理服务: {server_url}, 输出: {zip_output_path}")
    zip_text = process_document(
        file_path=pdf_path,
        processor=processor,
        server_url=server_url,
        output_path=zip_output_path,
        timeout=timeout,
    )


    return zip_output_path

def extract_zip_and_find_md(zip_path: str, extract_dir: Optional[str] = None) -> str:
    """解压 ZIP 并返回目录层级最深的 MD 文件绝对路径。"""
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"ZIP 文件不存在: {zip_path}")
    if extract_dir is None:
        base_dir = os.path.dirname(zip_path)
        extract_dir = os.path.join(base_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)
    md_candidates = []
    for root, _, files in os.walk(extract_dir):
        for fn in files:
            lower_fn = fn.lower()
            if lower_fn.endswith('.md') and not lower_fn.endswith('_fix.md'):
                md_candidates.append(os.path.join(root, fn))
    if not md_candidates:
        raise FileNotFoundError(f"未在解压目录中找到 md 文件: {extract_dir}")
    md_path = max(md_candidates, key=lambda p: p.count(os.sep))
    return os.path.abspath(md_path)

def save_with_sanitized_name(local_path: str) -> str:
    abs_path = os.path.abspath(local_path)
    if not os.path.isfile(abs_path):
        print(f"文件不存在: {abs_path}")
        raise FileNotFoundError(abs_path)
    dir_name = os.path.dirname(abs_path) # 包含文件名的目录路径
    filename = os.path.basename(abs_path) # 包含扩展名的文件名
    title, ext = os.path.splitext(filename) # 文件名（无扩展名）和扩展名
    safe_title = _safe_filename(title) or "unnamed"
    target = os.path.join(dir_name, f"{safe_title}{ext}")
    if os.path.abspath(target) == abs_path:
        return abs_path
    if os.path.exists(target):
        i = 2
        while True:
            cand = os.path.join(dir_name, f"{safe_title}_{i}{ext}")
            if not os.path.exists(cand):
                target = cand
                break
            i += 1
    os.rename(abs_path, target)
    return os.path.abspath(target)

def rewrite_md_images_to_http(md_path: str,
                              base_host: str = "http://10.18.11.98:8081",
                              workspace_root: str = "/home/amlogic") -> int:
    """
    将 Markdown 中的相对图片链接（形如 `![](images/xxx.jpg)` 或 `![alt](images/xxx.png)`）
    重写为以 `base_host` 为前缀的绝对 HTTP 链接。

    目标示例：
    `![](<base_host>/<rel_dir>/images/a330da6d4c400b09729b6f9d67a5f48c0aae40f48c984fce0a18f2ee53893f61.jpg)`
    其中 `<rel_dir>` 是 md 所在目录相对 `workspace_root` 的路径（保留空格，不进行 URL 编码）。

    返回修改的链接数量。
    """
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"MD 文件不存在: {md_path}")

    md_dir = os.path.dirname(md_path)
    # 计算相对路径用于拼接到 HTTP 前缀（按用户示例不做 URL 编码）
    try:
        rel_dir = os.path.relpath(md_dir, workspace_root)
    except Exception:
        # 回退：直接使用绝对路径去掉前导斜杠
        rel_dir = md_dir.lstrip(os.sep)

    http_base = f"{base_host}/{rel_dir}".replace("\\", "/")

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 匹配括号内以 images/ 或 ./images/ 开头的相对路径
    pattern = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>(?:\./)?images/[^)]+)\)")

    def _repl(m: re.Match) -> str:
        alt = m.group("alt")
        url = m.group("url")
        # 去掉可能的前缀 "./"
        if url.startswith("./"):
            url = url[2:]
        new_url = f"{http_base}/{url}"
        return f"![{alt}]({new_url})"

    new_content, count = pattern.subn(_repl, content)
    new_md = os.path.join(md_dir, f"{os.path.basename(md_path).replace('.md', '')}_with_img.md")
    if count > 0:
        with open(new_md, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"已重写 {count} 个图片链接为绝对 HTTP 路径: {http_base}/images/…")
    else:
        print("未发现需要重写的相对图片链接（images/…）")
        new_md = md_path

    return count, new_md

