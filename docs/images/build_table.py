"""retrieval-table.html을 PNG로 캡처한다(Windows의 Microsoft Edge 헤드리스, 2배 해상도).

  python docs/images/build_table.py

Edge가 다른 경로에 있으면 EDGE 환경 변수로 지정한다. 캡처 영역은 HTML 본문 크기에 맞춰 WIDTH·HEIGHT로 정한다.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDGE = os.getenv("EDGE", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
WIDTH, HEIGHT = 900, 256


def main() -> int:
    page = (HERE / "retrieval-table.html").resolve().as_uri()
    out = HERE / "retrieval-table.png"
    command = [EDGE, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
               f"--window-size={WIDTH},{HEIGHT}", f"--screenshot={out}", page]
    return subprocess.run(command).returncode


if __name__ == "__main__":
    sys.exit(main())
