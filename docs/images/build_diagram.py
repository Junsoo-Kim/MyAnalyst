"""<이름>.src.mmd의 로고 자리 표시자를 이미지 태그로 바꿔 <이름>.mmd를 만들고 <이름>.png로 렌더링한다.

  python docs/images/build_diagram.py                 # 모든 *.src.mmd
  python docs/images/build_diagram.py langgraph       # 하나만

자리 표시자: {{a,b,...}} 노드용(로고 20px), {{a:small}} 선 라벨용(14px), {{a,b:chip}} 진한 배경 위용(흰 바탕).
한 자리 표시자의 로고들은 가로로 붙인 SVG 한 장으로 합친다. 로고마다 이미지를 따로 넣으면 Mermaid가 노드 폭을
글자 기준으로 계산해 로고가 한 줄에 하나씩 세로로 쌓인다.
로고는 icons/*.svg를 data URI로 넣는다(렌더링이 외부 네트워크에 의존하지 않게). 그만큼 글자 수가 늘어
Mermaid 기본 제한(maxTextSize 50,000)을 넘으므로 설정에서 늘린다.
출처: devicon(MIT), Simple Icons(CC0). 각 로고의 상표권은 해당 소유자에게 있다.
렌더링에는 Node.js가 필요하다(npx로 @mermaid-js/mermaid-cli 실행).
"""
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIZES = {"": 20, "small": 14, "chip": 20}
GAP = 6


def data_uri(svg: bytes) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode()


def icon_tag(names: str, variant: str) -> str:
    logos = names.split(",")
    size = SIZES[variant]
    pad = 3 if variant == "chip" else 0
    width = len(logos) * size + (len(logos) - 1) * GAP + 2 * pad
    height = size + 2 * pad
    parts = []
    if variant == "chip":
        parts.append(f"<rect width='{width}' height='{height}' rx='5' fill='#FFFFFF'/>")
    for i, name in enumerate(logos):
        logo = data_uri((HERE / "icons" / f"{name}.svg").read_bytes())
        parts.append(f"<image href='{logo}' x='{pad + i * (size + GAP)}' y='{pad}' width='{size}' height='{size}'/>")
    composite = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
                 f"viewBox='0 0 {width} {height}'>{''.join(parts)}</svg>").encode()
    return f"<img src='{data_uri(composite)}' width='{width}' height='{height}' style='vertical-align:middle'/>"


def build(name: str) -> int:
    source = (HERE / f"{name}.src.mmd").read_text(encoding="utf-8")
    rendered = re.sub(r"\{\{([\w,]+)(?::(\w+))?\}\}", lambda m: icon_tag(m.group(1), m.group(2) or ""), source)
    (HERE / f"{name}.mmd").write_text(rendered, encoding="utf-8", newline="\n")
    config = HERE / ".mermaid-config.json"
    config.write_text(json.dumps({"securityLevel": "loose", "maxTextSize": 1000000, "flowchart": {"htmlLabels": True}}),
                      encoding="utf-8")
    try:
        command = ["npx", "-y", "@mermaid-js/mermaid-cli@11.4.2", "-i", f"{name}.mmd", "-o", f"{name}.png",
                   "-c", config.name, "-w", "1600", "-s", "2", "-b", "white"]
        return subprocess.run(command, cwd=HERE, shell=sys.platform == "win32").returncode
    finally:
        config.unlink(missing_ok=True)


def main() -> int:
    names = sys.argv[1:] or sorted(p.name[:-len(".src.mmd")] for p in HERE.glob("*.src.mmd"))
    return max(build(name) for name in names)


if __name__ == "__main__":
    sys.exit(main())
