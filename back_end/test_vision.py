
from pathlib import Path

from vision import understand_image


# 测试图片路径：先使用一张本地 JPG 或 PNG 图片
image_path = Path("test_wheat.jpg")

if not image_path.exists():
    raise FileNotFoundError(
        f"找不到测试图片：{image_path.resolve()}，"
        "请将一张 JPG 或 PNG 图片放到 back_end 目录下并命名为 test_wheat.jpg"
    )

if image_path.stat().st_size > 4 * 1024 * 1024:
    raise ValueError("图片超过 4 MB，请换一张较小的图片")

image_bytes = image_path.read_bytes()

question = (
    "请观察这张小麦图片，描述可见的叶片、颜色和斑点等特征。"
    "如果不能确定病害种类，请明确说明，不要仅凭图片武断诊断。"
)

try:
    result = understand_image(image_bytes, question)
    print("\n图片理解结果：")
    print(result)
except Exception as exc:
    print(f"\n图片理解调用失败：{type(exc).__name__}: {exc}")