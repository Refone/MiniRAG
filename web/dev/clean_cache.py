"""清理本应用在浏览器中的旧版本缓存（localStorage 旧 key）。

本轮重构不做旧缓存迁移（重构方案-反馈.md 第 3 条）：偏好改用全新
kb-preferences key 起步，本脚本输出一段 JS，在应用页面的 DevTools
Console 粘贴执行即可清除废弃的旧 key（localStorage 按 origin 隔离，
只能在该页面上下文内执行）。

用法: cd web/dev && python clean_cache.py
"""
import subprocess
import webbrowser

LEGACY_KEYS = ["kb_theme", "kb-chat-store", "kb-docs-store"]  # kb_session_id 保留，勿加

if __name__ == "__main__":
    snippet = ";".join(f'localStorage.removeItem("{k}")' for k in LEGACY_KEYS)
    print("请打开应用页面，在 DevTools Console 粘贴执行：\n")
    print(f"  {snippet}\n")
    # 顺手复制到剪贴板（macOS pbcopy；失败静默，不影响主流程）
    try:
        subprocess.run(["pbcopy"], input=snippet, text=True, check=True, timeout=5)
        print("（已复制到剪贴板）")
    except Exception:
        pass
    webbrowser.open("http://localhost:5173/")
    print("（已尝试打开应用页面 http://localhost:5173/）")
