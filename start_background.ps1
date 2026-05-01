Write-Host "Starting AI Strategic War Room in Background..."

# Start Backend Server
Start-Process -FilePath "python" -ArgumentList "-m uvicorn main:app --reload --port 8000" -WorkingDirectory ".\backend" -WindowStyle Minimized

# Start Frontend Server
Start-Process -FilePath "python" -ArgumentList "-m http.server 3001" -WorkingDirectory ".\frontend" -WindowStyle Minimized

Write-Host "Servers started successfully in minimized windows."
Write-Host "Frontend is mapped to: http://localhost:3001"
Write-Host "Backend API is mapped to: http://localhost:8000"
