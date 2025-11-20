import os
import sys
import zipfile
import re
from typing import Optional

try:
    import requests
except ImportError:
    print("缺少依赖: 请先安装 requests —— pip install requests", file=sys.stderr)
    raise

# 依赖本地模块
from my_confluce_test import export_confluence_page_to_pdf_by_url, _safe_filename
from process_client import process_document

class SkipProcessing(Exception):
    """输出目录已存在，跳过本轮处理。"""
    pass


def _post_md_path(md_abs_path: str, webhook_url: str, timeout: int = 10):
    """将 MD 文件的绝对路径发送到指定 webhook，并返回响应对象。"""
    payload = {"path": md_abs_path}
    headers = {"Content-Type": "application/json"}
    print(f"发送 webhook 请求，等待响应… URL: {webhook_url}")
    resp = requests.post(webhook_url, json=payload, headers=headers, timeout=timeout)
    print(f"Webhook 响应状态: {resp.status_code}")
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # 打印部分响应体，便于定位错误
        body_preview = resp.text[:200] if hasattr(resp, 'text') else '<no text>'
        print(f"Webhook 返回错误: {e}; 响应体预览: {body_preview}", file=sys.stderr)
        raise
    return resp


def send_md_path_to_webhook(md_path: str, webhook_url: Optional[str], timeout: int = 10) -> bool:
    """发送 MD 文件绝对路径到 webhook。

    返回 True 表示发送成功；未提供 webhook 或发送失败返回 False。
    """
    if not webhook_url:
        return False
    md_abs_path = os.path.abspath(md_path)
    try:
        resp = _post_md_path(md_abs_path, webhook_url, timeout=timeout)
        print(f"已发送 MD 绝对路径到 webhook: {webhook_url}\n路径: {md_abs_path}\n状态码: {resp.status_code}")
        return True
    except Exception as e:
        print(f"发送 webhook 失败: {e}", file=sys.stderr)
        return False


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
    :return: Markdown 文本
    """
    pdf_path = ''
    # 1) 从 URL 导出 PDF
    print(f"开始导出 PDF，URL: {page_url}")
    if not page_url or not page_url.strip():
        raise ValueError("Confluence 页面 URL 不能为空")
    if not page_url.startswith("https://"):
        pdf_path = page_url
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


def _parse_args(argv):
    import argparse

    parser = argparse.ArgumentParser(description="通过 Confluence URL 导出 PDF 并转换为 Markdown")
    # parser.add_argument("--url", required=True, help="Confluence 页面完整 URL")
    parser.add_argument("--processor", default="mineru", help="处理器名称")
    parser.add_argument("--server", default="http://10.58.11.60:7890/process/zip", help="处理服务 URL")
    parser.add_argument("--pdf", default="/home/amlogic/RAG/debug_doc", help="可选：PDF 输出路径")
    parser.add_argument("--out", default="output.zip", help="可选：ZIP 输出路径")
    parser.add_argument("--timeout", type=int, default=6000, help="请求超时时间(秒)")
    parser.add_argument(
        "--webhook",
        # default="http://localhost:5678/webhook-test/0ccf68cf-97d7-4361-b3b5-3cdea3a244c7", #测试webhook
        default="http://localhost:5678/webhook/0ccf68cf-97d7-4361-b3b5-3cdea3a244c7", #生产的webhook
        help="可选：接收 MD 绝对路径的 webhook URL（置空则不发送）",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    # urls = [
    #     "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088204",
    #     # "/home/amlogic/RAG/debug_doc/WiFi基本介绍及常见调试方法.pdf",
    # ]
    # urls = [
    # "https://confluence.amlogic.com/display/SW/Video+decoder+debug+print+config",
    # "https://confluence.amlogic.com/pages/viewpage.action?pageId=364792684#AudioHaldump/debugintroduction-a.ms12versionpipeline",
    # "https://confluence.amlogic.com/pages/viewpage.action?pageId=165291970",
    # "https://confluence.amlogic.com/pages/viewpage.action?pageId=100811852"
    # ]
    urls = [
    "https://confluence.amlogic.com/display/SW/Video+decoder+debug+print+config",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=364792684#AudioHaldump/debugintroduction-a.ms12versionpipeline",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=165291970",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=100811852"
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088161",
    "https://confluence.amlogic.com/display/SW/How+to+debug+in+multi_instance+mode",
    "https://confluence.amlogic.com/display/SW/How+to+do+video+decoder+performace+test",
    "https://confluence.amlogic.com/display/SW/How+to+do+decoded+YUV+crc+verification",
    "https://confluence.amlogic.com/display/SW/DDR+access+urgent+seting+for+decoder+or+GPU",
    "https://confluence.amlogic.com/display/SW/How+to+dump+decoded+YUV+data",
    "https://confluence.amlogic.com/display/SW/HDR+data+Process+in+video+decoder",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088204",
    "https://confluence.amlogic.com/display/SW/Force+DI+in+decoder+driver",
    "https://confluence.amlogic.com/display/SW/Multi-instance+decoder+information++tutorial",
    "https://confluence.amlogic.com/display/SW/Performance+test+method+in+AFBC+and+non-AFBC+mode",
    "https://confluence.amlogic.com/display/SW/Video+decoder+ucode+introduction",
    "https://confluence.amlogic.com/display/SW/MACRO+defines+in+h264+single+ucode",
    "https://confluence.amlogic.com/display/SW/Qucik+guidence+for+decoder+crash+issue",
    "https://confluence.amlogic.com/display/SW/Memory+pollution+issue+debug+with+DMC",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088229",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088232",
    "https://confluence.amlogic.com/display/SW/Simple+tools+for+decoder+debug",
    "https://confluence.amlogic.com/display/SW/Stream+buf+data+dump",
    "https://confluence.amlogic.com/display/SW/Video+decoder+debug+print+config",
    "https://confluence.amlogic.com/display/SW/Error+handle+policy",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=160995650",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088232",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=180740926",
    "https://confluence.amlogic.com/display/SW/Decoder+data+dump+for+5.15",
    ]
    import time
    error_urls = []
    succ_pdfs = []
    for url in urls:
        time.sleep(3)
        try:
            zip_output_path = url_to_zip(
                # page_url=args.url,
                page_url=url,
                processor=args.processor,
                server_url=args.server,
                pdf_out=args.pdf,
                md_out=args.out,
                timeout=args.timeout,
                webhook_url=args.webhook,
            )
        except SkipProcessing as e:
            print(f"{e}，跳过本轮")
            continue
        except Exception as e:
            print(f"处理失败: {e}", file=sys.stderr)
            error_urls.append(url)
            continue

        print(f"已保存 zip 至: {zip_output_path}")
        try:
            md_path = extract_zip_and_find_md(zip_output_path)
            print(f"已提取 MD 文件: {md_path}")
        except Exception as e:
            print(f"解压或查找 MD 失败: {e}", file=sys.stderr)
            error_urls.append(url)
            continue
        # md_path = "/home/amlogic/RAG/debug_doc/AudioHal dump_debug introduction/extracted/AudioHal dump_debug introduction/vlm/AudioHal dump_debug introduction.md"
        # 重写 MD 中的相对图片链接为绝对 HTTP 链接
        try:
            rewritten, new_md_path = rewrite_md_images_to_http(
                md_path,
                base_host="http://10.18.11.98:8081",
                workspace_root="/home/amlogic",
            )
            print(f"图片链接重写完成，共修改 {rewritten} 处")
        except Exception as e:
            print(f"图片链接重写失败: {e}", file=sys.stderr)
            error_urls.append(url)
            continue

        succ_pdfs.append(new_md_path)

    local_file_dir = os.path.dirname(__file__)
    succ_pdfs_save_dir = os.path.join(local_file_dir, "succ_pdfs.txt")
    with open(succ_pdfs_save_dir, "w") as f:
        for pdf in succ_pdfs:
            f.write(pdf + "\n")
    # 发送 MD 路径到 webhook（如提供），并同步打印返回内容
    # new_md_path = "/home/amlogic/RAG/debug_doc/WiFi基本介绍及常见调试方法/extracted/WiFi基本介绍及常见调试方法/vlm/WiFi基本介绍及常见调试方法_with_img.md"
    # new_md_path = "/home/amlogic/RAG/debug_doc/Video_decoder_debug_print_config/extracted/Video_decoder_debug_print_config/vlm/Video_decoder_debug_print_config.md"
    # new_md_path = "/home/amlogic/RAG/debug_doc/Decoder_data_dump_for_5.15/extracted/Decoder_data_dump_for_5.15/vlm/Decoder_data_dump_for_5.15.md"
    with open(succ_pdfs_save_dir, "r") as f:
        for line in f:
            line = line.strip()
            webhook_resp = send_md_path_to_webhook(line, args.webhook, timeout=args.timeout)
            if webhook_resp is not None:
                print(f"Webhook 返回内容: {webhook_resp}")
    
    print(f"处理完成，共处理 {len(urls)} 个 URL，{len(error_urls)} 个 URL 处理失败")
    if error_urls:
        print(f"失败 URL 列表: {error_urls}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())