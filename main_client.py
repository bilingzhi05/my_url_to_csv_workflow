import os
import sys
import time

from download_minueru import (
    url_to_zip,
    extract_zip_and_find_md,
    SkipProcessing,
    rewrite_md_images_to_http,
)
from send_to_n8n_webhook import send_md_path_to_webhook

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
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(timestamp, exist_ok=True)
    local_file_dir = os.path.dirname(__file__)
    import time
    error_urls = []
    minueru_succ_pdfs = []

    
    urls = [
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=364792684#AudioHaldump/debugintroduction-a.ms12versionpipeline",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=165291970",
    "https://confluence.amlogic.com/pages/viewpage.action?pageId=100811852",
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
    "/home/amlogic/RAG/debug_doc/SDK使用指南(Android S).docx",
    "/home/amlogic/RAG/debug_doc/Android U SDK User Guide_0.1.docx",
    ]

    # 需要自动化,不校验md文档，放开以下代码
    # for i, url in enumerate(urls):
    #     print(f"准备处理第 {i+1}/{len(urls)} URL: {url},随时可以断开")
    #     time.sleep(3)
    #     print(f"正在处理中,请勿断开")
    #     time.sleep(1)
    #     try:
    #         zip_output_path = url_to_zip(
    #             # page_url=args.url,
    #             page_url=url,
    #             processor=args.processor,
    #             server_url=args.server,
    #             pdf_out=args.pdf,
    #             md_out=args.out,
    #             timeout=args.timeout,
    #             webhook_url=args.webhook,
    #         )
    #     except SkipProcessing as e:
    #         print(f"{e}，跳过本轮")
    #         continue
    #     except Exception as e:
    #         print(f"处理失败: {e}", file=sys.stderr)
    #         error_urls.append(url)
    #         continue

    #     print(f"已保存 zip 至: {zip_output_path}")
    #     try:
    #         md_path = extract_zip_and_find_md(zip_output_path)
    #         print(f"已提取 MD 文件: {md_path}")
    #     except Exception as e:
    #         print(f"解压或查找 MD 失败: {e}", file=sys.stderr)
    #         error_urls.append(url)
    #         continue
    #     minueru_succ_pdfs.append(md_path)
    
    # #保存从mineru 解析成功的md文档
    # succ_pdfs_path = os.path.join(local_file_dir, timestamp, f"succ_from_mineru_pdfs_{timestamp}.txt")
    # with open(succ_pdfs_path, "w") as f:
    #     for pdf in minueru_succ_pdfs:
    #         f.write(pdf + "\n")
    # 到这里结束

  
    # 需要自动化,不校验md文档，放开以下代码
    new_md_paths = []
    succ_pdfs_path = "/home/amlogic/RAG/debug_doc/my_url_to_csv/my_url_to_csv_workflow/20251120_151847/succ_from_mineru_pdfs_20251120_151847.txt"
    with open(succ_pdfs_path, "r") as f:
        for md_path in f:
            md_path = md_path.strip()
            new_md_path = ''

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
                error_urls.append(md_path)
                continue
            # 保存从改写成功的md文档,可以用来给webhook单独调试
            new_md_paths.append(new_md_path)
            webhook_resp = send_md_path_to_webhook(new_md_path, args.webhook, timeout=args.timeout)
            if webhook_resp is not None:
                print(f"Webhook 返回内容: {webhook_resp}")

    succ_to_webhook_path = os.path.join(local_file_dir, timestamp, f"succ_check_img_pdfs_{timestamp}.txt")
    with open(succ_to_webhook_path, "w") as f:
        for pdf in new_md_paths:
            f.write(pdf + "\n")

    if error_urls:
        print("失败 URL 列表:\n" + "\n".join(error_urls))
    error_urls_path = os.path.join(local_file_dir, timestamp, f"error_urls_{timestamp}.txt")
    with open(error_urls_path, "w") as f:
        for pdf in error_urls:
            f.write(pdf + "\n")
    # 到这里结束
    print(f"处理完成，共处理 {len(urls)} 个 URL，{len(error_urls)} 个 URL 处理失败")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
