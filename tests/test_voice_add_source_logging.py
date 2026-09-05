from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_voice_add_source_path_is_visible_at_info_level():
    # The source path is diagnostic output users need to see without global DEBUG logging.
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'logger.info(f"[AiriVoice] 获取到本地音频路径: {local_path}")' in main
