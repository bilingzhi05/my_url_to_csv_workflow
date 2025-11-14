
from urllib.error import HTTPError
import re
from urllib.parse import urlparse, parse_qs
import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from atlassian  import Confluence
import markdown2

###################配置区#########################
space = "ST"
logs_status_page_name = "日志数据信息统计页" # 日志需要更新到的页面
COMPARE_LOGS_STATUS_TABLE_ID = 0
DIAGNOSE_TABLE_ID = 1

confluence_url = 'https://confluence.amlogic.com/'
#username = 'nan.li'
#password = 'abc.1234'
username = "lingzhi.bi"
password = "Qwer!2345"
# username = "nan.li"
# password = "**.deng110110"

space = 'ST'
#####################################################

class aml_confluence:
    def __init__(self):
        self.mConfluence = Confluence(url=confluence_url, username=username, password=password, verify_ssl = False)
    def __str__(self):
        return f"{self.mConfluence}"

def create_confluence_page(confluence:Confluence, parent_id:int, body:str, title:str, space:int)->int:
    try:
        # 发起请求时禁用 SSL 证书验证
        response = confluence.update_or_create(title=title, parent_id=parent_id, body=body, full_width=False)
        # print(response)
        if response is None:
            print(f"create_confluence_page--->Failed to create page {title}")
            return None
        # 获取页面 ID
        page_id = response.get("id")
        print(page_id)
        # 检查页面 ID 是否存在
        if not page_id:
            print(f"create_confluence_page--->Failed to create page {title}")
            return None
        
        return page_id
    except HTTPError as e:
        print(f"create_confluence_page {title}--->HTTP error occurred: {e}")
        return None

def get_page_cotent_by_id(confluence:Confluence, page_id:int) -> str:
    page_content = confluence.get_page_by_id(page_id=page_id,expand="body.storage,version")
    if page_content is None:
        print("get_page_cotent_by_id--->page_content is None")
        return ""
    return page_content["body"]["storage"]["value"]

def clear_all_rows_except_first(table):
    rows = table.find_all("tr")
    for i, row in enumerate(rows):
        if i != 0:  # 跳过第一行
            row.extract()
    return table

def confluence_instance_build()->Confluence:
    confluence_mine = aml_confluence()
    return confluence_mine.mConfluence

def add_rows_to_table(soup, table, rows):
    #参数判空
    if table is None or rows is None:
        return
    
    # 遍历多行数据
    for row_content in rows:
        # 创建新的<tr>元素并填充内容
        new_row = soup.new_tag("tr")
        for cell_content in row_content:
            new_cell = soup.new_tag("td")
            if cell_content is None :
                new_cell.string = " "
            else:
                new_cell.string = cell_content
            new_row.append(new_cell)
            # 将新行插入到表格中
            table.append(new_row)

def update_logs_status_page(jira_mine = None, confluence = None, page_name = logs_status_page_name, table_id = 0, get_table = None):
    column_count = 0
    if get_table is None or confluence is None:
        print("update_logs_status_page--->get_table function/confluence")
        return
    try:
        
        tamplate_page_id = confluence.get_page_id(space, page_name)
        print(f"tamplate_page_id:{tamplate_page_id}")
        
        tamplate_page_content = get_page_cotent_by_id(confluence, tamplate_page_id)
        # print(tamplate_page_content)

        #使用BeautifulSoup解析page的内容
        soup = BeautifulSoup(tamplate_page_content, "html.parser")
        # 找到所有的表格
        tables = soup.find_all('table')
        if len(tables) <= table_id:
            print("update_logs_status_page--->table_id is out of range")
            return
        # print(tables[SE_F_TABLE_ID])
        table_tmp = tables[table_id]
        clear_all_rows_except_first(table_tmp)
        expand_table_rows = get_table(jira_mine)
        column_count = len(expand_table_rows)
        add_rows_to_table(soup, table_tmp, expand_table_rows)

        # print(table_tmp)

        # 创建一个新页面
        # new_page_id = create_confluence_page(confluence, parent_id=140483564, body=f"{soup.prettify()}", title="test_demo1", space=space)
        # if new_page_id is None:
        #     print("create_confluence_page--->Failed to create page")

        confluence.update_page(page_id=tamplate_page_id, title=page_name,  body=f"{soup.prettify()}",representation='storage',  full_width=False)
        print("confluence page edit Success!")
        # 打开一个文件以写入模式
        # with open("output.html", "w", encoding="utf-8") as file:
        #     # 将美化后的HTML代码写入文件
        #     file.write(soup.prettify())
    except Exception as e:
        print(e)
    return column_count

def copy_page_to_new_page(confluence, from_page_id, new_page_name,parent_id):
    result = False
    #检查参数
    if confluence is None:
        print("copy_page_to_new_page bad param!")
        return result 
    try:
        # tamplate_page_id = confluence.get_page_id(space, tamplate_page_name)
        print(f"tamplate_page_id:{from_page_id}")
        
        tamplate_page_content = get_page_cotent_by_id(confluence, from_page_id)
        # print(tamplate_page_content)

        #使用BeautifulSoup解析page的内容
        soup = BeautifulSoup(tamplate_page_content, "html.parser")
        new_page_id = create_confluence_page(confluence, parent_id=parent_id, body=f"{soup.prettify()}", title=new_page_name, space=space)
        if new_page_id is None:
            print("create_confluence_page--->Failed to create page")
            return result
        else:
            result = True
            print(f"create confluence page {new_page_name} Success!")
    except Exception as e:
        print(e)
    return result

def  page_exist(confluence, page_name)->bool:
    return confluence.page_exists(space, page_name, type=None)

def get_pdf_download_url_by_page_url(confluence:Confluence, page_url:str) -> str:
    if page_url is None or len(page_url.strip()) == 0:
        return ""
    try:
        parsed = urlparse(page_url)
        qs = parse_qs(parsed.query)
        page_id = None
        if "pageId" in qs and len(qs["pageId"]) > 0:
            page_id = qs["pageId"][0]
        else:
            m = re.search(r"/pages/(\d+)/", parsed.path)
            if m:
                page_id = m.group(1)
        if page_id is None:
            try:
                page = confluence.get_confluence_page_by_url(page_url)
                if page and isinstance(page, dict):
                    pid = page.get("id") or page.get("pageId") or page.get("contentId")
                    if pid:
                        page_id = str(pid)
            except Exception:
                pass
        if page_id is None:
            return ""
        return f"{confluence_url.rstrip('/')}/spaces/flyingpdf/pdfpageexport.action?pageId={page_id}"
    except Exception:
        return ""

def get_page_title_by_url(confluence:Confluence, page_url:str) -> str:
    if page_url is None or len(page_url.strip()) == 0:
        return ""
    try:
        parsed = urlparse(page_url)
        qs = parse_qs(parsed.query)
        page_id = None
        if "pageId" in qs and len(qs["pageId"]) > 0:
            page_id = qs["pageId"][0]
        else:
            m = re.search(r"/pages/(\d+)/", parsed.path)
            if m:
                page_id = m.group(1)
        if page_id:
            try:
                page = confluence.get_page_by_id(page_id)
                if page and isinstance(page, dict):
                    t = page.get("title")
                    if t:
                        return t
            except Exception:
                pass
        try:
            page = confluence.get_confluence_page_by_url(page_url)
            if page and isinstance(page, dict):
                t = page.get("title")
                if t:
                    return t
        except Exception:
            pass
        return ""
    except Exception:
        return ""

def sanitize_filename(name:str) -> str:
    if name is None:
        return ""
    s = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    s = s.replace(" ", "_")
    s = s.strip()
    if len(s) == 0:
        return ""
    return s[:200]

def export_confluence_page_to_pdf_by_url(url:str) -> str:

    try:
        confluence = confluence_instance_build()
        # url = "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088161"
        pdf_url = get_pdf_download_url_by_page_url(confluence, url)
        print(f"pdf_url:{pdf_url}")
        pdf_save_path = ''
        if pdf_url:
            pid = parse_qs(urlparse(pdf_url).query).get("pageId", [None])[0]
            title = get_page_title_by_url(confluence, url)
            safe_title = sanitize_filename(title) if title else f"confluence_page_{pid or 'unknown'}"
            filename = f"{safe_title}.pdf"
            resp = requests.get(pdf_url, auth=(username, password), verify=False, stream=True)
            if resp.status_code == 200:
                with open(filename, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                pdf_save_path = os.path.abspath(filename)
                print(f"pdf_save_path:{pdf_save_path}")
            else:
                print(f"download_pdf_failed status:{resp.status_code}")
            return pdf_save_path
    except Exception as e:
        print(e)

if __name__ == "__main__":
    # url = "https://confluence.amlogic.com/pages/viewpage.action?pageId=18088161"
    url = "https://confluence.amlogic.com/display/SW/Video+decoder+debug+print+config"
    pdf_save_path = export_confluence_page_to_pdf_by_url(url)
    if pdf_save_path:
        print(f"export_confluence_page_to_pdf_by_url Success! pdf_save_path:{pdf_save_path}")
    else:
        print(f"export_confluence_page_to_pdf_by_url Failed!")
