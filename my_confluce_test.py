import os
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse, parse_qs, unquote
CONFLUENCE_USER = "nan.li"
CONFLUENCE_PASS = "**.deng110110"
# 配置 Confluence 访问信息
CONFLUENCE_BASE_URL = "https://confluence.amlogic.com"
CONFLUENCE_USERNAME = CONFLUENCE_USER  # 建议通过环境变量传递用户名
CONFLUENCE_PASSWORD = CONFLUENCE_PASS  # 建议通过环境变量传递密码

def get_confluence_page_by_url(page_url):
    """
    根据完整的 Confluence 页面 URL 获取页面内容。
    兼容以下常见格式：
    - https://confluence.example.com/display/SPACEKEY/Page+Title
    - https://confluence.example.com/pages/viewpage.action?pageId=123456
    - https://confluence.example.com/wiki/display/SPACEKEY/Page+Title
    - https://confluence.example.com/wiki/pages/viewpage.action?pageId=123456
    :param page_url: 页面完整 URL
    :return: 页面 JSON 数据
    """
    parsed = urlparse(page_url)
    qs = parse_qs(parsed.query)
    # print(f"qs: {qs}")
    # 1) 优先支持 pageId 形式的链接
    if "pageId" in qs and qs["pageId"]:
        page_id = qs["pageId"][0]
        return get_confluence_page(page_id)

    # 2) 支持 /display/{SPACE}/{Title} 和 /wiki/display/{SPACE}/{Title}
    path = parsed.path or ""
    marker = "/display/"
    if "/wiki/display/" in path:
        marker = "/wiki/display/"

    idx = path.find(marker)
    if idx != -1:
        rest = path[idx + len(marker):]
        parts = rest.split("/")
        # 至少应包含 SPACEKEY 和 Title
        if len(parts) >= 2:
            space_key = parts[0]
            title_part = "/".join(parts[1:])  # 兼容标题中意外的斜杠分段
            page_title = unquote(title_part).replace("+", " ")

            # 通过标题和 space key 查询页面 ID
            url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
            params = {
                "title": page_title,
                "spaceKey": space_key,
                "expand": "body.storage"
            }
            auth = HTTPBasicAuth(CONFLUENCE_USERNAME, CONFLUENCE_PASSWORD)
            headers = {"Accept": "application/json"}
            response = requests.get(url, auth=auth, headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                raise ValueError("未找到指定页面")
            page_id = results[0]["id"]
            return get_confluence_page(page_id)

    # 3) 其他格式暂不支持
    raise ValueError("无效的 Confluence 页面 URL：不支持的链接格式")

def get_confluence_page(page_id):
    """
    根据 page_id 获取 Confluence 页面内容
    :param page_id: 页面 ID
    :return: 页面 JSON 数据
    """
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}?expand=body.storage"
    auth = HTTPBasicAuth(CONFLUENCE_USERNAME, CONFLUENCE_PASSWORD)
    headers = {"Accept": "application/json"}
    response = requests.get(url, auth=auth, headers=headers)
    response.raise_for_status()
    return response.json()

def get_confluence_space_pages(space_key, limit=25):
    """
    获取指定空间下的页面列表
    :param space_key: 空间 key
    :param limit: 返回页面数量上限
    :return: 页面列表 JSON 数据
    """
    base_api = f"{CONFLUENCE_BASE_URL}/rest/api"
    auth = HTTPBasicAuth(CONFLUENCE_USERNAME, CONFLUENCE_PASSWORD)
    headers = {"Accept": "application/json"}

    # 先校验空间是否存在且可访问
    space_url = f"{base_api}/space/{space_key}"
    space_resp = requests.get(space_url, auth=auth, headers=headers)
    if space_resp.status_code == 404:
        raise ValueError(f"空间 '{space_key}' 不存在或无访问权限")
    space_resp.raise_for_status()

    # 优先使用 /space/{key}/content 获取页面列表
    list_url = f"{base_api}/space/{space_key}/content"
    list_params = {
        "type": "page",
        "limit": limit
    }
    list_resp = requests.get(list_url, auth=auth, headers=headers, params=list_params)
    if list_resp.status_code == 404:
        # 回退到 /content?spaceKey=... 方式（兼容不同版本的 Confluence）
        fallback_url = f"{base_api}/content"
        fallback_params = {
            "spaceKey": space_key,
            "type": "page",
            "limit": limit,
            "expand": "version,body.storage"
        }
        fallback_resp = requests.get(fallback_url, auth=auth, headers=headers, params=fallback_params)
        fallback_resp.raise_for_status()
        data = fallback_resp.json()
        # 统一返回结构
        return {"results": data.get("results", [])}

    list_resp.raise_for_status()
    data = list_resp.json()
    # /space/{key}/content 返回在 'page.results' 下，统一为 'results'
    return {"results": data.get("page", {}).get("results", [])}

def _safe_filename(name: str) -> str:
    """将标题转为安全的文件名。"""
    # 替换可能导致文件名不合法的字符
    return (
        name.strip()
            .replace('/', '_')
            .replace('\\', '_')
            .replace(':', '_')
            .replace('*', '_')
            .replace('?', '_')
            .replace('"', '_')
            .replace('<', '_')
            .replace('>', '_')
            .replace('|', '_')
            .replace(' ', '_')
    )

def export_confluence_page_to_word(page_id: str, out_file: str | None = None) -> str:
    """
    导出指定页面为 Word（.doc）文件。
    优先尝试 Server/DC 端点，其次兼容 Cloud 端点。
    :param page_id: Confluence 页面 ID
    :param out_file: 输出文件路径（可选）。未提供时从标题或 Content-Disposition 推断。
    :return: 保存的文件路径
    """
    auth = HTTPBasicAuth(CONFLUENCE_USERNAME, CONFLUENCE_PASSWORD)
    headers = {"Accept": "application/msword"}

    candidates = [
        f"{CONFLUENCE_BASE_URL}/pages/exportwordpage.action?pageId={page_id}",  # Server/DC 通常使用
        f"{CONFLUENCE_BASE_URL}/exportword?pageId={page_id}",                   # Cloud 兼容
        f"{CONFLUENCE_BASE_URL}/wiki/exportword?pageId={page_id}",              # Cloud 带 wiki 前缀
    ]

    last_error = None
    for url in candidates:
        try:
            resp = requests.get(url, auth=auth, headers=headers, stream=True)
            if resp.status_code == 200:
                # 推断文件名（含空值与空白的健壮回退）
                filename = None
                cd = resp.headers.get('Content-Disposition')
                if cd and 'filename=' in cd:
                    filename = cd.split('filename=')[-1].strip('"')
                if not filename or not str(filename).strip():
                    # 尝试用页面标题
                    page = get_confluence_page(page_id)
                    filename = _safe_filename(page.get('title', f"confluence_page_{page_id}")) + '.doc'

                target = (out_file if out_file and str(out_file).strip() else filename)
                # 写入到磁盘
                with open(target, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return target
            else:
                last_error = f"HTTP {resp.status_code} for {url}"
        except Exception as e:
            last_error = str(e)
            continue

    raise RuntimeError(f"导出失败，已尝试多个端点：{last_error}")

def export_confluence_page_to_pdf(page_id: str, out_file: str | None = None) -> str:
    """
    导出指定页面为 PDF 文件。
    优先尝试 Server/DC 端点，其次兼容 Cloud 端点。
    :param page_id: Confluence 页面 ID
    :param out_file: 输出文件路径（可选）。未提供时从标题或 Content-Disposition 推断。
    :return: 保存的文件路径
    """
    auth = HTTPBasicAuth(CONFLUENCE_USERNAME, CONFLUENCE_PASSWORD)
    headers = {"Accept": "application/pdf"}

    candidates = [
        f"{CONFLUENCE_BASE_URL}/spaces/flyingpdf/pdfpageexport.action?pageId={page_id}",  # 常见 Server/DC 导出端点
        f"{CONFLUENCE_BASE_URL}/pages/pdfpageexport.action?pageId={page_id}",             # 另一常见端点
        f"{CONFLUENCE_BASE_URL}/wiki/spaces/flyingpdf/pdfpageexport.action?pageId={page_id}",  # Cloud 带 wiki 前缀
        f"{CONFLUENCE_BASE_URL}/wiki/pages/pdfpageexport.action?pageId={page_id}",
    ]

    last_error = None
    for url in candidates:
        try:
            resp = requests.get(url, auth=auth, headers=headers, stream=True)
            if resp.status_code == 200:
                filename = None
                cd = resp.headers.get('Content-Disposition')
                if cd and 'filename=' in cd:
                    filename = cd.split('filename=')[-1].strip('"')
                if not filename or not str(filename).strip():
                    page = get_confluence_page(page_id)
                    filename = _safe_filename(page.get('title', f"confluence_page_{page_id}")) + '.pdf'

                target = (out_file if out_file and str(out_file).strip() else filename)
                with open(target, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return target
            else:
                last_error = f"HTTP {resp.status_code} for {url}"
        except Exception as e:
            last_error = str(e)
            continue

    raise RuntimeError(f"PDF 导出失败，已尝试多个端点：{last_error}")

def export_confluence_page_to_word_by_url(page_url: str, out_file: str | None = None) -> str:
    """
    通过页面 URL 导出为 Word。
    :param page_url: 页面完整 URL，如 https://confluence.amlogic.com/display/SW/Video+decoder+debug+print+config
    :param out_file: 输出路径（可选）
    :return: 保存的文件路径
    """
    page_json = get_confluence_page_by_url(page_url)
    page_id = page_json.get('id')
    title = page_json.get('title', f"confluence_page_{page_id}")
    default_name = _safe_filename(title) + '.doc'
    return export_confluence_page_to_word(page_id, out_file or default_name)

def export_confluence_page_to_pdf_by_url(page_url: str, out_file: str | None = None) -> str:
    """
    通过页面 URL 导出为 PDF。
    :param page_url: 页面完整 URL
    :param out_file: 输出路径（可选）
    :return: 保存的文件路径
    """
    page_json = get_confluence_page_by_url(page_url)
    # print(f"page_json:{page_json}")
    page_id = page_json.get('id')
    title = page_json.get('title', f"confluence_page_{page_id}")
    default_name = _safe_filename(title) + '.pdf'
    target = default_name
    if out_file and str(out_file).strip():
        p = out_file
        if os.path.isdir(p) or p.endswith(os.sep):
            os.makedirs(p, exist_ok=True)
            target = os.path.join(p, default_name)
        else:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            target = p
    return export_confluence_page_to_pdf(page_id, target)

if __name__ == "__main__":
    # 示例：通过 URL 获取页面内容
    # try:
    #     page_url = "https://confluence.amlogic.com/display/SW/Video+decoder+debug+print+config"
    #     page_data = get_confluence_page_by_url(page_url)
    #     print("页面标题:", page_data["title"])
    #     print("页面内容:", page_data["body"]["storage"]["value"])
    # except Exception as e:
    #     print("获取页面失败:", e)

    # # 示例：将上述页面导出为 Word（.doc）
    # try:
    #     saved_path = export_confluence_page_to_word_by_url(page_url)
    #     print("导出为 Word 成功，文件路径:", saved_path)
    # except Exception as e:
    #     print("导出为 Word 失败:", e)

    # 示例：导出为 PDF
    # page_url = "https://confluence.amlogic.com/display/SW/Video+decoder+debug+print+config"
    # page_url = "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088161"
    page_url = "https://confluence.amlogic.com/pages/viewpage.action?pageId=180740926"
    try:
        output_dir = "/home/amlogic/RAG/debug_doc"
        pdf_path = export_confluence_page_to_pdf_by_url(page_url, output_dir)
        print("导出为 PDF 成功，文件路径:", pdf_path)
    except Exception as e:
        print("导出为 PDF 失败:", e)

    # # 示例：使用你提供的页面ID直接导出 PDF
    # try:
    #     provided_page_id = "88531908"
    #     pdf_path2 = export_confluence_page_to_pdf(provided_page_id)
    #     print("按页面ID导出为 PDF 成功，文件路径:", pdf_path2)
    # except Exception as e:
    #     print("按页面ID导出为 PDF 失败:", e)

    # # 示例：获取空间 key 为 "DEV" 的前 25 个页面
    # try:
    #     space_pages = get_confluence_space_pages("SW", limit=25)
    #     for page in space_pages.get("results", []):
    #         print("页面标题:", page["title"], "页面 ID:", page["id"])
    # except Exception as e:
    #     print("获取空间页面失败:", e)
