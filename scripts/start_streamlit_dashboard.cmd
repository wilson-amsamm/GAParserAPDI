@echo off
setlocal
cd /d "C:\Users\Administrator\DevProjs\OnlinePlatformAnalytics"
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m streamlit run streamlit_app.py --server.headless true --server.address 0.0.0.0 --server.port 8508
endlocal
