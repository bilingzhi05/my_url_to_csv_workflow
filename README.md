# my_url_to_csv_workflow
# mineru fastapi 启动服务
cd /home/nan.li/ && source work/MyMinerU/.venv/bin/activate && uvicorn work.fastapi_zip_service.my_url_to_csv_workflow.app.main:app --host 0.0.0.0 --port 7890 &
# 启动url 转 QAcsv
cd /home/amlogic/RAG/debug_doc/my_url_to_csv/my_url_to_csv_workflow/ && python3 main_client.py
