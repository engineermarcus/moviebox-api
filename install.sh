apt update && apt install zip -y
pip install -r  requirements.txt --break-system-packages && python3 -m playwright install --with-deps chromium

