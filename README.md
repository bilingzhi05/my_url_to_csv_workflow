# my_url_to_csv_workflow
# mineru fastapi 启动服务
cd /home/nan.li/ && source work/MyMinerU/.venv/bin/activate && uvicorn work.fastapi_zip_service.app.main:app --host 0.0.0.0 --port 7890 &
# 启动url 转 QAcsv
python3 download_minueru.py
