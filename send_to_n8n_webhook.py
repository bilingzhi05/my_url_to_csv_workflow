from typing import Optional
import requests
import sys
import os



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

if __name__ == "__main__":

    # 需要自动化,不校验md文档，放开以下代码
    # new_md_path = "/home/amlogic/RAG/debug_doc/How_to_do_video_decoder_performace_test/extracted/How_to_do_video_decoder_performace_test/vlm/How_to_do_video_decoder_performace_test.md"
    new_md_path = "/home/amlogic/RAG/debug_doc/0_iotrace使用/extracted/0_iotrace使用/vlm/0_iotrace使用.md"
    webhook_url = "http://localhost:5678/webhook/0ccf68cf-97d7-4361-b3b5-3cdea3a244c7"
    webhook_test_url = "http://localhost:5678/webhook-test/0ccf68cf-97d7-4361-b3b5-3cdea3a244c7"
    webhook_resp = send_md_path_to_webhook(new_md_path, webhook_url, timeout=600)
    new_md_paths = []
    if webhook_resp is not None:
        print(f"Webhook 返回内容: {webhook_resp}")