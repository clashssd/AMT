"""
Тесты для Agnes media generation.

Запуск:
    python tests/test_agnes_media.py

Требования:
    - API-ключ Agnes (из настроек AMT или env AMT_AGNES_KEY)
    - Base URL Agnes (https://apihub.agnes-ai.com/v1)
"""
import os
import sys
import json
import time

# Добавляем backend в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from ai_engine import media as media_gen


def get_agnes_config():
    """Возвращает (base_url, api_key, video_model, image_model)."""
    base_url = "https://apihub.agnes-ai.com/v1"
    api_key = os.environ.get("AMT_AGNES_KEY", "")
    video_model = os.environ.get("AMT_AGNES_VIDEO_MODEL", "agnes-video-2.5")
    image_model = os.environ.get("AMT_AGNES_IMAGE_MODEL", "agnes-image-2.5-flash")
    return base_url, api_key, video_model, image_model


def test_image_generation():
    """Тест генерации картинки через Agnes."""
    base_url, api_key, _, image_model = get_agnes_config()
    if not api_key:
        print("⚠️  AMT_AGNES_KEY не задан — пропускаю тест картинки")
        return None

    print("🎨 Тест генерации картинки (Agnes)...")
    result = media_gen.generate_image_ref(
        base_url=base_url,
        api_key=api_key,
        model=image_model,
        prompt="A red cube on a white background",
        size="512x512",
    )
    print(f"   ok: {result.get('ok')}")
    print(f"   code: {result.get('code', '')}")
    if result.get("b64"):
        print(f"   b64: {result['b64'][:50]}... (длина {len(result['b64'])})")
    if result.get("url"):
        print(f"   url: {result['url'][:80]}...")
    if result.get("error"):
        print(f"   error: {result['error']}")
    return result


def test_video_generation():
    """Тест генерации видео через Agnes."""
    base_url, api_key, video_model, _ = get_agnes_config()
    if not api_key:
        print("⚠️  AMT_AGNES_KEY не задан — пропускаю тест видео")
        return None

    print("🎬 Тест генерации видео (Agnes)...")
    result = media_gen.generate_video(
        base_url=base_url,
        api_key=api_key,
        model=video_model,
        prompt="A cat walking on a table",
        duration="5",
        aspect_ratio="16:9",
    )
    print(f"   ok: {result.get('ok')}")
    print(f"   code: {result.get('code', '')}")
    print(f"   task_id: {result.get('task_id', '')}")
    print(f"   video_id: {result.get('video_id', '')}")
    print(f"   model_name: {result.get('model_name', '')}")
    print(f"   agnes: {result.get('agnes')}")
    if result.get("url"):
        print(f"   url: {result['url'][:80]}...")
    if result.get("error"):
        print(f"   error: {result['error']}")

    # Если есть task_id — опрашиваем статус
    if result.get("ok") and result.get("task_id"):
        task_id = result["task_id"]
        model_name = result.get("model_name", "")
        print(f"\n   ⏳ Опрашиваем статус задачи {task_id} (каждые 5 сек, макс 60 сек)...")
        for i in range(12):
            time.sleep(5)
            status = media_gen.check_video_task(
                base_url=base_url,
                api_key=api_key,
                task_id=task_id,
                model_name=model_name,
            )
            st = status.get("status", "")
            print(f"   [{(i+1)*5}s] status={st}, progress={status.get('progress', '')}")
            if st in ("completed", "succeeded"):
                print(f"   ✅ Видео готово!")
                if status.get("url"):
                    print(f"   url: {status['url'][:80]}...")
                return status
            if st in ("failed", "error"):
                print(f"   ❌ Ошибка: {status.get('error', '')}")
                return status
        print("   ⚠️  Таймаут опроса (60 сек)")
    return result


def test_video_polling():
    """Тест опроса видео-задачи (если task_id задан через env)."""
    base_url, api_key, video_model, _ = get_agnes_config()
    task_id = os.environ.get("AMT_TEST_VIDEO_TASK_ID", "")
    if not task_id:
        print("⚠️  AMT_TEST_VIDEO_TASK_ID не задан — пропускаю тест опроса")
        return None
    if not api_key:
        print("⚠️  AMT_AGNES_KEY не задан — пропускаю тест опроса")
        return None

    print(f"📡 Тест опроса видео-задачи {task_id}...")
    result = media_gen.check_video_task(
        base_url=base_url,
        api_key=api_key,
        task_id=task_id,
        model_name=video_model,
    )
    print(f"   status: {result.get('status')}")
    print(f"   progress: {result.get('progress', '')}")
    if result.get("url"):
        print(f"   url: {result['url'][:80]}...")
    if result.get("error"):
        print(f"   error: {result['error']}")
    return result


def main():
    print("=" * 60)
    print("AMT: Тесты Agnes media generation")
    print("=" * 60)

    base_url, api_key, video_model, image_model = get_agnes_config()
    print(f"\nBase URL: {base_url}")
    print(f"API Key: {'задан' if api_key else 'НЕ задан (AMT_AGNES_KEY)'}")
    print(f"Video Model: {video_model}")
    print(f"Image Model: {image_model}")
    print()

    results = {}

    # Картинка
    img_result = test_image_generation()
    results["image"] = img_result

    # Видео
    vid_result = test_video_generation()
    results["video"] = vid_result

    # Опрос (если задан task_id)
    poll_result = test_video_polling()
    results["video_polling"] = poll_result

    # Итог
    print("\n" + "=" * 60)
    print("ИТОГ")
    print("=" * 60)
    for name, r in results.items():
        if r is None:
            print(f"  {name}: пропущен")
        elif r.get("ok"):
            print(f"  {name}: ✅ ok")
        else:
            print(f"  {name}: ❌ {r.get('code', 'error')}: {r.get('error', '')[:100]}")


if __name__ == "__main__":
    main()
