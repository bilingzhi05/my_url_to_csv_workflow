import os
import sys
from typing import Optional
import time

try:
    import requests
except ImportError as e:
    print("缺少依赖: 请先安装 requests —— pip install requests", file=sys.stderr)
    raise


def process_document(
    file_path: str,
    processor: str = "mineru",
    server_url: str = "http://10.58.11.60:7890/process/zip",
    output_path: Optional[str] = "output.zip",
    timeout: int = 120,
) -> str:
    start_time = time.time()
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f)}
        data = {"processor": processor}
        resp = requests.post(server_url, files=files, data=data, timeout=timeout)
        resp.raise_for_status()

    # 解析返回文件名（如有）
    cd = resp.headers.get("Content-Disposition", "")
    target_path = output_path
    if not target_path or not str(target_path).strip():
        filename = "output.zip"
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip('"')
        target_path = filename

    # 确保目录存在（若指定了目录）
    dir_name = os.path.dirname(target_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    # 写入二进制 ZIP 内容
    with open(target_path, "wb") as out:
        out.write(resp.content)
    
    end_time = time.time()
    print(f"minueru 处理完成，耗时: {end_time - start_time} 秒")
    return target_path


def _parse_args(argv):
    import argparse

    parser = argparse.ArgumentParser(description="上传文件到处理服务并保存 ZIP 输出")
    parser.add_argument("--file", default="/home/amlogic/RAG/debug_doc/SDK使用指南_Android_S_.docx", required=False, help="待处理文件路径")
    parser.add_argument("--processor", default="mineru", help="处理器名称")
    parser.add_argument(
        "--server",
        default="http://10.58.11.60:7890/process/zip",
        help="处理服务URL",
    )
    parser.add_argument("--out", default="output.zip", help="输出 ZIP 文件路径")
    parser.add_argument("--timeout", type=int, default=6000, help="请求超时时间(秒)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        process_document(
            file_path=args.file,
            processor=args.processor,
            server_url=args.server,
            output_path=args.out,
            timeout=args.timeout,
        )
    except requests.HTTPError as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    print(f"已保存输出: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())