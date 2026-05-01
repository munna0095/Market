$env:PYTHONIOENCODING = "utf-8"
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 3
Set-Location "C:\Users\Admin\Desktop\Share_Market\backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
